#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Replay a `claude plugin eval` suite through the GitHub Copilot CLI.

Reads the same case files (prompt.md, case.yaml, graders/*.md), runs each
case with and without the plugin's skills installed in the workspace, grades
the result with the same grader types, and writes an aggregate-result.json in
the same shape as `claude plugin eval --json`. LLM graders are judged by
`claude -p`, so Claude and Copilot runs share one judge.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

TOOL_MAP = {  # Claude tool name -> Copilot transcript tool name(s)
    "Skill": ["skill"],
    "Read": ["view"],
    "Grep": ["rg", "grep"],
    "Glob": ["glob", "rg"],
    "Bash": ["bash", "shell"],
    "Write": ["create", "write", "edit"],
    "Edit": ["edit", "str_replace_editor"],
}
JUDGE_VOTES = 3


# ---------- case loading ----------

def split_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    return (yaml.safe_load(m.group(1)) or {}), m.group(2)


def load_cases(eval_dir: Path) -> list[dict]:
    cases = []
    for d in sorted(p for p in eval_dir.rglob("*") if p.is_dir()):
        if d.name in ("results", "graders", "mocks") or "results" in d.parts:
            continue
        pm, cy = d / "prompt.md", d / "case.yaml"
        if not pm.exists() and not cy.exists():
            continue
        case: dict = {"dir": d, "name": d.name, "runs": 3, "max_turns": 10,
                      "timeout_seconds": 300, "context": {}, "graders": []}
        if cy.exists():
            y = yaml.safe_load(cy.read_text()) or {}
            case.update({k: v for k, v in y.items() if k not in ("execution", "graders")})
            case.update(y.get("execution") or {})
            for i, g in enumerate(y.get("graders") or []):
                g = dict(g)
                g.setdefault("name", f"grader-{i}")
                case["graders"].append(g)
        if pm.exists():
            fm, body = split_frontmatter(pm.read_text())
            case.update(fm)
            case["prompt"] = body.strip()
        gd = d / "graders"
        if gd.exists():
            for gf in sorted(gd.glob("*.md")):
                fm, body = split_frontmatter(gf.read_text())
                fm["name"] = gf.stem
                fm["body"] = body.strip()
                case["graders"].append(fm)
        if not case["graders"]:
            sys.exit(f"case {case['name']}: no graders")
        cases.append(case)
    return cases


# ---------- transcript parsing ----------

def parse_tool_calls(transcript: str) -> list[dict]:
    """Return [{tool, input}] in call order from a Copilot --share transcript."""
    calls = []
    for m in re.finditer(r"^### `([^`]+)`\n(.*?)(?=^---\s*$|\Z)", transcript, re.S | re.M):
        tool, block = m.group(1), m.group(2)
        j = re.search(r"```json\n(.*?)\n```", block, re.S)
        calls.append({"tool": tool, "input": j.group(1) if j else block.strip()})
    return calls


def tool_matches(call: dict, tool: str, input_match: str | None) -> bool:
    names = TOOL_MAP.get(tool, [tool.lower()])
    if call["tool"] not in names:
        return False
    return not input_match or re.search(input_match, call["input"]) is not None


# ---------- graders ----------

def target_text(target, run: dict) -> str:
    if target in (None, "last_message"):
        return run["last_message"]
    if target == "trace":
        return run["transcript"]
    if target == "files":
        return "\n".join(run["created_files"])
    if isinstance(target, dict) and target.get("source") == "file":
        p = Path(run["workspace"]) / target["path"]
        return p.read_text() if p.exists() else ""
    raise ValueError(f"unsupported target {target!r}")


def judge(rubric: str, evidence: str, model: str) -> tuple[list[bool], str]:
    prompt = (
        "You are grading an AI coding agent's output against a rubric.\n\n"
        f"<rubric>\n{rubric}\n</rubric>\n\n<output>\n{evidence}\n</output>\n\n"
        "Decide whether the output satisfies the rubric. Reply with one line of "
        "reasoning, then on the last line exactly PASS or FAIL."
    )
    votes = []
    for _ in range(JUDGE_VOTES):
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--output-format", "json",
             "--max-turns", "1"],
            capture_output=True, text=True, cwd=tempfile.gettempdir())
        try:
            text = json.loads(r.stdout).get("result", "")
        except json.JSONDecodeError:
            text = r.stdout
        last = text.strip().splitlines()[-1].strip().upper() if text.strip() else "FAIL"
        votes.append(last.startswith("PASS"))
    return votes, evidence


def grade(g: dict, run: dict, judge_model: str) -> dict:
    t = g["type"]
    res = {"name": g["name"], "weight": g.get("weight", 1), "passed": False,
           "explanation": "", "evidence": None}
    if t == "regex":
        text = target_text(g.get("target"), run)
        n = len(re.findall(g["pattern"], text, re.I if "i" in str(g.get("flags", "")) else 0))
        mode = str(g.get("match", "contains"))
        if mode == "contains":
            res["passed"] = n > 0
        elif mode == "not_contains":
            res["passed"] = n == 0
        elif mode.startswith("count:"):
            res["passed"] = n == int(mode.split(":")[1])
        res["explanation"] = f"{n} match(es) for /{g['pattern']}/"
    elif t == "tool_used":
        n = sum(tool_matches(c, g["tool"], g.get("input_match")) for c in run["tool_calls"])
        lo, hi = g.get("min", 1), g.get("max")
        res["passed"] = n >= lo and (hi is None or n <= hi)
        res["explanation"] = f"{n} call(s) to {g['tool']}"
    elif t == "tool_order":
        def first(spec):
            tool, im = (spec, None) if isinstance(spec, str) else (spec["tool"], spec.get("input_match"))
            return next((i for i, c in enumerate(run["tool_calls"]) if tool_matches(c, tool, im)), None)
        a, b = first(g["before"]), first(g["after"])
        res["passed"] = a is not None and b is not None and a < b
        res["explanation"] = f"before at {a}, after at {b}"
    elif t == "file_exists":
        hit = any(fnmatch.fnmatch(f, g["path"]) for f in run["created_files"])
        res["passed"] = hit if g.get("exists", True) else not hit
        res["explanation"] = f"created files: {run['created_files']}"
    elif t == "llm":
        evidence = target_text(g.get("focus"), run)
        votes, evidence = judge(g["body"], evidence, judge_model)
        res["passed"] = sum(votes) * 2 > len(votes)
        res["judgeVotes"] = votes
        res["explanation"] = "judge votes: " + " ".join("PASS" if v else "FAIL" for v in votes)
        res["evidence"] = evidence
    else:
        res["explanation"] = f"grader type {t} not supported on copilot; skipped"
        res["skipped"] = True
    return res


# ---------- running ----------

def snapshot(ws: Path) -> set[str]:
    return {str(p.relative_to(ws)) for p in ws.rglob("*")
            if p.is_file() and not any(x in p.parts for x in (".git", ".claude", "_eval"))}


def run_once(case: dict, arm: str, skills_dir: Path, args, out_dir: Path, idx: int) -> dict:
    ws = Path(tempfile.mkdtemp(prefix="copilot-eval-"))
    evald = ws / "_eval"
    evald.mkdir()
    run = {"arm": arm, "workspace": str(ws), "error": None, "turns": None,
           "costUsd": None, "startedAt": datetime.now(timezone.utc).isoformat()}
    t0 = time.time()
    try:
        script = case.get("context", {}).get("scaffold_script")
        if script and args.scaffold:
            env = {"PATH": os.environ["PATH"], "HOME": str(ws / "_eval"), "TMPDIR": str(evald), "TERM": "dumb"}
            r = subprocess.run(["bash", str(case["dir"] / script)], cwd=ws, env=env,
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(f"scaffold failed: {r.stderr[-500:]}")
        if arm == "with":
            shutil.copytree(skills_dir, ws / ".claude" / "skills")
        before = snapshot(ws)
        cmd = ["copilot", "-p", case["prompt"], "--allow-all-tools", "--no-custom-instructions",
               "--silent", "--share", str(evald / "transcript.md"),
               "--log-dir", str(evald / "logs"), "--log-level", "debug"]
        if args.model:
            cmd += ["--model", args.model]
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True,
                           timeout=case.get("timeout_seconds", 300))
        run["last_message"] = r.stdout.strip()
        (evald / "answer.md").write_text(run["last_message"])
        if r.returncode != 0:
            run["error"] = f"copilot exit {r.returncode}: {r.stderr.strip()[-500:]}"
        tp = evald / "transcript.md"
        run["transcript"] = tp.read_text() if tp.exists() else ""
        run["tool_calls"] = parse_tool_calls(run["transcript"])
        run["turns"] = len(run["tool_calls"])
        run["created_files"] = sorted(snapshot(ws) - before)
        logs = list((evald / "logs").glob("*.log"))
        models = set()
        for lg in logs:
            models.update(re.findall(r'turn tool surface resolved \{"model":"([^"]+)"', lg.read_text(errors="ignore")))
        run["modelObserved"] = sorted(models)
    except Exception as e:  # noqa: BLE001
        run["error"] = str(e)
        run.setdefault("last_message", "")
        run.setdefault("transcript", "")
        run.setdefault("tool_calls", [])
        run.setdefault("created_files", [])
        run.setdefault("modelObserved", [])
    run["durationSeconds"] = round(time.time() - t0)

    ablate = args.ablation == "with-without"
    graders = []
    for g in case["graders"]:
        res = grade(g, run, args.judge_model) if not run["error"] else \
            {"name": g["name"], "weight": g.get("weight", 1), "passed": False, "explanation": "run error"}
        with_only = g.get("arm") == "with-only" or (g["type"] == "tool_used" and g.get("tool") == "Skill")
        res["withOnly"] = with_only and g.get("arm") != "both"
        res["scored"] = not (ablate and res["withOnly"]) and not res.get("skipped")
        graders.append(res)
    scored = [g for g in graders if g["scored"]]
    tw = sum(g["weight"] for g in scored)
    run["score"] = round(sum(g["weight"] for g in scored if g["passed"]) / tw, 4) if tw else 0.0
    run["passed"] = run["score"] >= args.threshold
    run["graders"] = graders

    keep = out_dir / case["name"] / f"{arm}-{idx}"
    shutil.copytree(evald, keep)
    run["tracePath"] = str(keep)
    for k in ("transcript", "tool_calls", "workspace"):
        run.pop(k)
    shutil.rmtree(ws, ignore_errors=True)
    return run


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default=".", help="plugin root")
    ap.add_argument("--eval-dir", default="evals")
    ap.add_argument("--runs", type=int)
    ap.add_argument("--case", help="glob on case name")
    ap.add_argument("--tag", action="append")
    ap.add_argument("--ablation", choices=["none", "with-without"], default="with-without")
    ap.add_argument("--model", help="copilot --model (omit for Copilot's auto mode)")
    ap.add_argument("--judge-model", default="haiku", help="model for `claude -p` judge")
    ap.add_argument("--scaffold", action="store_true", help="run each case's scaffold_script")
    ap.add_argument("--threshold", type=float, default=1.0)
    ap.add_argument("--output-dir")
    args = ap.parse_args()

    root = Path(args.target).resolve()
    eval_dir = root / args.eval_dir
    skills_dir = root / "skills"
    cases = load_cases(eval_dir)
    if args.case:
        cases = [c for c in cases if fnmatch.fnmatch(c["name"], args.case)]
    if args.tag:
        cases = [c for c in cases if set(c.get("tags", [])) & set(args.tag)]
    if not cases:
        sys.exit("no cases matched")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = Path(args.output_dir) if args.output_dir else eval_dir / "results" / f"{stamp}-copilot"
    out_dir.mkdir(parents=True)
    vout = subprocess.run(["copilot", "--version"], capture_output=True, text=True).stdout
    copilot_version = (re.search(r"\d+\.\d+\.\d+", vout) or re.search(r"\S+", vout)).group(0)
    arms = ["with", "without"] if args.ablation == "with-without" else ["with"]
    print(f"Agent: copilot {copilot_version} (model: {args.model or 'auto'}), judge: claude {args.judge_model}")
    print(f"{len(arms)} arm(s) x {len(cases)} case(s)")

    t0 = time.time()
    results = []
    for case in cases:
        n = args.runs or case.get("runs", 3)
        runs = {a: [] for a in arms}
        for arm in arms:
            for i in range(1, n + 1):
                r = run_once(case, arm, skills_dir, args, out_dir, i)
                runs[arm].append(r)
                print(f"  {case['name']} run {i}/{n} [{arm}]: score {r['score']:.2f}"
                      f"  model {','.join(r['modelObserved']) or '?'}" + (f"  ERROR {r['error']}" if r["error"] else ""))
                for g in r["graders"]:
                    mark = "✓" if g["passed"] else "✗"
                    tag = "" if g["scored"] else " (indicator)"
                    print(f"    {mark} {g['name']} (weight {g['weight']}){tag}: {g['explanation']}")
        mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
        agg = {"score": mean([r["score"] for r in runs["with"]]),
               "passRate": mean([float(r["passed"]) for r in runs["with"]])}
        if "without" in runs:
            agg["scoreWithout"] = mean([r["score"] for r in runs["without"]])
            agg["passRateWithout"] = mean([float(r["passed"]) for r in runs["without"]])
            agg["delta"] = round(agg["score"] - agg["scoreWithout"], 4)
        results.append({"name": case["name"], "dir": str(case["dir"].relative_to(root)),
                        "promptMarkdown": case["prompt"], "runsPerCase": n,
                        "graders": [{k: v for k, v in g.items() if k != "body"} for g in case["graders"]],
                        "arms": runs, "aggregates": agg})

    deltas = [c["aggregates"].get("delta") for c in results if c["aggregates"].get("delta") is not None]
    report = {
        "schemaVersion": 1, "agent": "copilot", "copilotVersion": copilot_version,
        "model": args.model or "auto", "judgeModel": args.judge_model, "judge": "claude",
        "startedAt": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
        "durationSeconds": round(time.time() - t0), "costUsd": None,
        "suite": str(eval_dir),
        "aggregates": {"overallScore": round(sum(c["aggregates"]["score"] for c in results) / len(results), 4),
                       "casesPassed": sum(c["aggregates"]["score"] >= args.threshold for c in results),
                       "casesTotal": len(results),
                       "meanDelta": round(sum(deltas) / len(deltas), 4) if deltas else None},
        "cases": results,
    }
    (out_dir / "aggregate-result.json").write_text(json.dumps(report, indent=2))

    print()
    print(f"{'CASE':<28}{'WITH':>6}{'W/OUT':>7}{'Δ':>7}  RUNS")
    for c in results:
        a = c["aggregates"]
        wo = f"{a['scoreWithout']:.2f}" if "scoreWithout" in a else "-"
        d = f"{a['delta']:+.2f}" if "delta" in a else "-"
        print(f"{c['name']:<28}{a['score']:>6.2f}{wo:>7}{d:>7}  {c['runsPerCase'] * len(arms)}")
    print(f"\n{len(results)} case(s) · mean Δ {report['aggregates']['meanDelta']} · {report['durationSeconds']}s")
    print(f"Results: {out_dir / 'aggregate-result.json'}")
    return 0 if report["aggregates"]["casesPassed"] == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
