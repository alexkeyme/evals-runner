# evals-tryout

A plugin with one skill (`skills/code-review`) and an eval suite for it in the `claude plugin eval` format.

## Layout

- `.claude-plugin/plugin.json` - plugin manifest; `claude plugin eval` needs it
- `skills/code-review/SKILL.md` - the skill under test
- `evals/<case>/prompt.md` - the prompt and run limits for one case
- `evals/<case>/case.yaml` - context such as a scaffold script
- `evals/<case>/fixture.sh` - builds the workspace (a small git repo plus `changes.diff`) before the run
- `evals/<case>/graders/*.md` - one check per file; types are `llm` (rubric judged by a model), `regex`, `tool_used`, `tool_order`, `file_exists`
- `evals/results/` - written by each run, ignored by git
- `scripts/eval_copilot.py`, `scripts/report.py` - the Copilot runner and the HTML report renderer, see below

## Run

```sh
claude plugin eval . --scaffold --trust-plugin --no-publish --json evals/results/last.json
```

Useful variations:

```sh
claude plugin eval . --scaffold --trust-plugin --no-publish --case approves-clean-change --runs 1   # one case, one run
claude plugin eval . --scaffold --trust-plugin --no-publish --judge-model sonnet                    # stronger judge (default: haiku)
claude plugin eval . --scaffold --trust-plugin --no-publish --model sonnet                          # override the agent model
claude plugin eval . --scaffold --trust-plugin --no-publish --ablation none                         # skip the baseline arm
```

Ablation is on by default: each case runs `runs` times with the skill and `runs` times without it (the baseline arm), and the report shows both scores and the delta. `runs` and `model` are set per case in `prompt.md` frontmatter and can be overridden with `--runs` and `--model`. Graders on `tool_used: Skill` are indicators and do not count toward the score.

Each run writes `evals/results/<timestamp>/aggregate-result.json` and `report.html`. Neither file records the agent or judge model, so use `--output-dir` to name the directory after the models when comparing them.

## Cases

- `approves-clean-change` - a correct refactor with matching tests. One `llm` grader fails the run if the review invents a bug, a security problem or missing tests. The expected verdict is APPROVE. Runs once per arm with `model: haiku`.

Cases worth adding next: a diff with a planted security bug that must be flagged as a BLOCKER with a REQUEST CHANGES verdict, and a non-review prompt where the skill must not fire (`tool_used: Skill` with `min: 0`, `max: 0`, `arm: both`).

## Run the same suite through GitHub Copilot

`scripts/eval_copilot.py` replays the case files through the Copilot CLI. It needs `uv` and a logged-in `copilot`.

```sh
uv run scripts/eval_copilot.py . --scaffold
uv run scripts/eval_copilot.py . --scaffold --runs 1 --ablation none --case approves-clean-change
```

How it maps to the Claude run:

- Workspace: same scaffold script, run in a temp dir. The "with" arm copies `skills/` into `<workspace>/.claude/skills/`, where Copilot picks them up. The "without" arm has no skills dir.
- Agent: `copilot -p` with `--no-custom-instructions` so your own AGENTS.md stays out. Copilot's auto mode picks the model; pass `--model` to pin one your plan allows. The `model` field in `prompt.md` is a Claude model name and is ignored here. The concrete model each run used is read from the debug log and stored as `modelObserved`.
- Graders: `regex`, `tool_used`, `tool_order`, `file_exists` work on the `--share` transcript. Claude tool names are mapped (Skill→skill, Read→view, Grep→rg, Bash→bash). `llm` graders are judged by `claude -p` with three votes, so Claude and Copilot runs share one judge. `baseline` and mock graders are skipped.
- Ablation: on by default, same as the Claude command. `--ablation none` runs only the with-skill arm.
- Output: `evals/results/<timestamp>-copilot/aggregate-result.json` in the shape of Claude's file, plus `agent`, `model`, `judgeModel` fields, and a `report.html` rendered from it. Each run's answer, transcript and debug log are kept in `<case>/<arm>-<n>/` next to it.
- `scripts/report.py <aggregate-result.json>` renders the HTML report for any result file, including one written by `claude plugin eval --json`. Reports are themed by agent: GitHub colors and badge for Copilot, the Claude palette and badge for Claude.
