#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Render an aggregate-result.json (from claude plugin eval or eval_copilot.py) to report.html,
in the same layout as the report claude plugin eval writes."""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

CSS = """
:root{--plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--ink-3:#6b6a64;--hairline:rgba(11,11,11,.10);
--inset:rgba(11,11,11,.04);--accent:#2a78d6;--base-fill:#6b6a64;--good:#067d06;--warning:#8a6100;--critical:#d03b3b;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--ink-3:#898781;
--hairline:rgba(255,255,255,.10);--inset:rgba(255,255,255,.05);--accent:#3987e5;--base-fill:#898781;--good:#0ca30c;--warning:#fab219;--critical:#e06c6c}}
*{box-sizing:border-box}body{margin:0;background:var(--plane);color:var(--ink);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:40px 24px 64px;display:flex;flex-direction:column;gap:20px}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
h1{margin:2px 0 0;font-size:24px;font-weight:600;line-height:1.25}h2{margin:0;font-size:17px;font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;color:var(--ink-2);font-size:13px}
.num{font-variant-numeric:tabular-nums lining-nums}.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}.muted{color:var(--ink-3)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--hairline);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.tile .label{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)}
.tile .value{font-size:26px;font-weight:600;line-height:1.1}.tile.hero .value{font-family:Georgia,serif;font-weight:400;font-size:48px}
.tile .sub{font-size:12px;color:var(--ink-2)}.delta-pos{color:var(--good)}.delta-neg{color:var(--critical)}
.howto{background:var(--surface);border:1px solid var(--hairline);border-radius:10px;padding:12px 16px;font-size:13px;color:var(--ink-2)}
.howto summary{cursor:pointer;color:var(--ink);font-weight:600}
section.case{background:var(--surface);border:1px solid var(--hairline);border-radius:10px;padding:16px 18px;display:flex;flex-direction:column;gap:12px}
.case-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.spacer{flex:1}.case-score{font-size:20px;font-weight:600}
.delta{font-size:13px;font-weight:600}.bar{height:6px;background:var(--inset);border-radius:3px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent)}.bar.base i{background:var(--base-fill)}
.arm-head{display:flex;gap:10px;align-items:baseline;margin-top:6px}.arm-label{font-weight:600}
.run{border-top:1px solid var(--hairline);padding:10px 0 4px}.run-head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.run-title{font-weight:600}.graders{display:flex;flex-direction:column;gap:6px;margin-top:8px}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;margin-right:6px}
.chip-pass{background:rgba(6,125,6,.12);color:var(--good)}.chip-fail{background:rgba(208,59,59,.12);color:var(--critical)}
.chip-ind{background:var(--inset);color:var(--ink-3)}.chip-err{background:rgba(138,97,0,.12);color:var(--warning)}
.grader-name{font-weight:600}.votes{letter-spacing:2px}details.ev{margin:4px 0 0 0}details.ev summary{cursor:pointer;font-size:12px;color:var(--ink-3)}
pre{background:var(--inset);border-radius:8px;padding:10px 12px;overflow:auto;white-space:pre-wrap;font-size:12.5px;margin:6px 0 0}
.error{color:var(--warning);font-size:13px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;
border:1px solid var(--hairline);background:var(--inset);color:var(--ink-2);vertical-align:middle;margin-left:8px}
.badge svg{width:14px;height:14px;fill:currentColor}
/* Copilot: GitHub Primer palette */
body.agent-copilot{--plane:#ffffff;--surface:#f6f8fa;--ink:#1f2328;--ink-2:#59636e;--ink-3:#6e7781;--hairline:#d1d9e0;
--inset:#eff2f5;--accent:#0969da;--base-fill:#8c959f;--good:#1a7f37;--warning:#9a6700;--critical:#cf222e;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif}
body.agent-copilot .tile.hero .value{font-family:inherit;font-weight:600;font-size:40px}
body.agent-copilot .tile,body.agent-copilot section.case,body.agent-copilot .howto{border-radius:6px;border-color:#d1d9e0}
body.agent-copilot .badge{background:#ddf4ff;border-color:#54aeff66;color:#0969da}
body.agent-copilot .eyebrow{color:#0969da}
@media (prefers-color-scheme:dark){body.agent-copilot{--plane:#0d1117;--surface:#161b22;--ink:#e6edf3;--ink-2:#9198a1;--ink-3:#8b949e;
--hairline:#30363d;--inset:#21262d;--accent:#2f81f7;--base-fill:#6e7681;--good:#3fb950;--warning:#d29922;--critical:#f85149}
body.agent-copilot .badge{background:#388bfd1a;border-color:#388bfd66;color:#58a6ff}body.agent-copilot .eyebrow{color:#58a6ff}}
/* Claude: warm paper palette with accent */
body.agent-claude{--accent:#d97757}
body.agent-claude .badge{background:#d9775722;border-color:#d9775766;color:#b85c3c}
body.agent-claude .eyebrow{color:#b85c3c}
"""

BADGES = {
    "copilot": '<span class=badge><svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>GitHub Copilot</span>',
    "claude": '<span class=badge><svg viewBox="0 0 16 16"><path d="M8 1l1.8 4.6L14.5 7l-4.2 2.1L8 15l-2.3-5.9L1.5 7l4.7-1.4z"/></svg>Claude Code</span>',
}



def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def pct(x) -> str:
    return "" if x is None else f"{round(x * 100)}%"


def fmt_delta(d) -> tuple[str, str]:
    if d is None:
        return "", ""
    cls = "delta-pos" if d > 0.005 else "delta-neg" if d < -0.005 else ""
    return f"{d * 100:+.1f} pts", cls


def render_run(r: dict, i: int, cost_known: bool) -> str:
    bits = [f"<span class=run-title>Run {i}</span>",
            f"<span class='num'>{pct(r.get('score'))}</span>",
            f"<span class=muted>{esc(r.get('turns'))} turns · {esc(r.get('durationSeconds'))}s"
            + (f" · ${r['costUsd']:.2f}" if cost_known and r.get("costUsd") is not None else "")
            + (f" · {esc(', '.join(r['modelObserved']))}" if r.get("modelObserved") else "") + "</span>"]
    if r.get("error"):
        bits.append(f"<span class=error>error: {esc(r['error'])}</span>")
    out = [f"<div class=run><div class=run-head>{' '.join(bits)}</div><div class=graders>"]
    for g in r.get("graders", []):
        scored = g.get("scored", True)
        if g.get("skipped"):
            chip = "<span class='chip chip-err'>skipped</span>"
        elif not scored:
            chip = f"<span class='chip chip-ind'>{'✓' if g['passed'] else '✗'} indicator</span>"
        else:
            chip = f"<span class='chip chip-{'pass' if g['passed'] else 'fail'}'>{'✓ pass' if g['passed'] else '✗ fail'}</span>"
        w = g.get("weight", 1)
        line = (f"<div>{chip}<span class=grader-name>{esc(g['name'])}</span>"
                + (f" <span class=muted>×{w}</span>" if w != 1 else "")
                + f" <span class=muted>{esc(g.get('explanation'))}</span>")
        if g.get("judgeVotes"):
            line += " <span class=votes>" + "".join("✓" if v else "✗" for v in g["judgeVotes"]) + "</span>"
        if g.get("evidence"):
            line += (f"<details class=ev{'' if g['passed'] else ' open'}><summary>Evidence (what the judge was shown)</summary>"
                     f"<pre>{esc(g['evidence'])}</pre></details>")
        out.append(line + "</div>")
    if r.get("tracePath"):
        out.append(f"<div class='muted mono'>artifacts: {esc(r['tracePath'])}</div>")
    out.append("</div></div>")
    return "\n".join(out)


def render(report: dict) -> str:
    a = report["aggregates"]
    cases = report["cases"]
    agent = report.get("agent", "claude")
    tool = "Copilot CLI" if agent == "copilot" else "Claude Code"
    version = report.get("copilotVersion") or report.get("claudeVersion", "")
    suite = report.get("suite", "")
    if isinstance(suite, dict):
        suite = suite.get("name") or suite.get("dir") or suite.get("plugin") or ""
    title = Path(str(suite)).parent.name or str(suite) or "evals"
    started = report.get("startedAt", "")
    try:
        started = datetime.fromisoformat(started.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        pass
    total_runs = sum(len(v) for c in cases for v in c["arms"].values())
    perfect = sum(1 for c in cases for v in c["arms"].values() for r in v if r.get("score") == 1)
    deltas = [c["aggregates"].get("delta") for c in cases if c["aggregates"].get("delta") is not None]
    ablated = bool(deltas)
    improved = sum(d > 0.005 for d in deltas); regressed = sum(d < -0.005 for d in deltas)
    flat = len(deltas) - improved - regressed
    base = [c["aggregates"]["scoreWithout"] for c in cases if "scoreWithout" in c["aggregates"]]
    base_mean = sum(base) / len(base) if base else None
    cost = report.get("costUsd")
    md, mcls = fmt_delta(a.get("meanDelta"))

    meta = [f"<span>{esc(tool)} v{esc(version)}</span>", f"<span class=num>{esc(started)}</span>",
            f"<span class=num>{esc(report.get('durationSeconds'))}s</span>"]
    if cost is not None:
        meta.append(f"<span class=num>${cost:.2f}</span>")
    meta += [f"<span class=num>{total_runs} runs</span>",
             f"<span>agent model {esc(report.get('model') or 'default')}</span>",
             f"<span>judge {esc(report.get('judgeModel') or 'haiku')}</span>"]

    out = [f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Eval report — {esc(agent)}</title><style>{CSS}</style></head><body class='agent-{esc(agent)}'><div class=wrap>",
           f"<header><div class=eyebrow>{esc(tool)} eval report</div><h1>{esc(title)}{BADGES.get(agent, "")}</h1>",
           f"<div class=meta>{''.join(meta)}</div></header>"]
    if ablated:
        out.append(f"<div class=howto>Plugin effect: <b class='{mcls}'>{md}</b> vs baseline — improved {improved} · flat {flat} · regressed {regressed} of {len(deltas)} case(s).</div>")
    tiles = [f"<div class='tile hero'><span class=label>Suite score · with plugin</span><span class='value num'>{pct(a.get('overallScore'))}</span><span class=sub>mean of per-case scores</span></div>"]
    if ablated:
        tiles.append(f"<div class=tile><span class=label>Ablation Δ</span><span class='value num {mcls}'>{md}</span><span class=sub>score points vs baseline</span></div>")
        tiles.append(f"<div class=tile><span class=label>Baseline score</span><span class='value num'>{pct(base_mean)}</span><span class=sub>without the plugin</span></div>")
    tiles.append(f"<div class=tile><span class=label>Cases</span><span class='value num'>{a.get('casesPassed')}</span><span class=sub>of {a.get('casesTotal')} passed</span></div>")
    tiles.append(f"<div class=tile><span class=label>Perfect runs</span><span class='value num'>{pct(perfect / total_runs if total_runs else None)}</span><span class=sub>runs where every grader passed</span></div>")
    out.append("<div class=tiles>" + "".join(tiles) + "</div>")
    out.append("<details class=howto><summary>How to read this report</summary><p>A run's score is the weighted fraction of its graders that passed. "
               "A case's score is the mean of its runs. The suite score is the mean of the per-case scores. Judge votes are independent samples of the LLM judge; "
               "the majority decides pass or fail. \"With plugin\" and \"Baseline\" runs are identical except for the plugin being loaded; Δ is the with-plugin score minus the baseline score. "
               "Graders marked <i>indicator</i> (such as whether the skill fired) show plugin activity but do not count toward the score.</p></details>")

    for c in cases:
        ca = c["aggregates"]
        d, dcls = fmt_delta(ca.get("delta"))
        out.append(f"<section class=case><div class=case-head><h2>{esc(c['name'])}</h2><span class='muted mono'>{esc(c.get('dir'))}</span>"
                   f"<span class=spacer></span>" + (f"<span class='delta {dcls}'>{d}</span>" if d else "")
                   + f"<span class='num case-score'>{pct(ca.get('score'))}</span></div>")
        out.append(f"<details><summary class=muted>Prompt</summary><pre>{esc(c.get('promptMarkdown'))}</pre></details>")
        for arm, label, cls in (("with", "With plugin", ""), ("without", "Baseline (no plugin)", "base")):
            runs = c["arms"].get(arm)
            if not runs:
                continue
            score = ca.get("score") if arm == "with" else ca.get("scoreWithout")
            perf = sum(1 for r in runs if r.get("score") == 1)
            out.append(f"<div class=arm-head><span class=arm-label>{label}</span><span class=num>{pct(score)}</span>"
                       f"<span class=muted>{pct(perf / len(runs))} of runs perfect</span></div>"
                       f"<div class='bar {cls}'><i style='width:{(score or 0) * 100:.0f}%'></i></div>")
            for i, r in enumerate(runs, 1):
                out.append(render_run(r, i, cost is not None))
        out.append("</section>")
    out.append("</div></body></html>")
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: report.py <aggregate-result.json>")
    src = Path(sys.argv[1])
    dst = src.with_name("report.html")
    dst.write_text(render(json.loads(src.read_text())))
    print(dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
