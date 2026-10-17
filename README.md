# evals-tryout

A plugin with one skill (`skills/code-review`) and an eval suite for it in the `claude plugin eval` format.

## Layout

- `.claude-plugin/plugin.json` - plugin manifest; `claude plugin eval` needs it
- `skills/code-review/SKILL.md` - the skill under test
- `evals/<case>/prompt.md` - the prompt and run limits for one case
- `evals/<case>/case.yaml` - context such as a scaffold script
- `evals/<case>/fixture.sh` - builds the workspace (a small git repo plus `changes.diff`) before the run
- `evals/<case>/graders/*.md` - one check per file: `llm` rubric, `regex`, `tool_used`
- `evals/results/` - written by each run, ignored by git

## Run

```sh
claude plugin eval . --scaffold --trust-plugin --no-publish --json evals/results/last.json
```

Useful variations:

```sh
claude plugin eval . --scaffold --case finds-sql-injection --runs 1   # one case, one run
claude plugin eval . --scaffold --tag smoke --judge-model sonnet      # stronger judge
claude plugin eval . --scaffold --model haiku                         # cheaper agent
```

Every case runs twice with the skill and twice without it (the baseline arm). The report shows the score of each arm and the delta. Graders on `tool_used: Skill` are indicators and do not count toward the score.

## Cases

- `finds-sql-injection` - must flag string-formatted SQL as a blocker, spot a pagination off-by-one, and request changes
- `approves-clean-change` - must not invent problems in a correct refactor and must approve
- `ignores-unrelated-request` - a Python question that is not a review; the skill must not fire

## Run the same suite through GitHub Copilot

`scripts/eval_copilot.py` replays the case files through the Copilot CLI. It needs `uv` and a logged-in `copilot`.

```sh
uv run scripts/eval_copilot.py . --scaffold
uv run scripts/eval_copilot.py . --scaffold --runs 1 --ablation none --case approves-clean-change
```

How it maps to the Claude run:

- Workspace: same scaffold script, run in a temp dir. The "with" arm copies `skills/` into `<workspace>/.claude/skills/`, where Copilot picks them up. The "without" arm has no skills dir.
- Agent: `copilot -p` with `--no-custom-instructions` so your own AGENTS.md stays out. Copilot's auto mode picks the model; pass `--model` to pin one your plan allows. The concrete model each run used is read from the debug log and stored as `modelObserved`.
- Graders: `regex`, `tool_used`, `tool_order`, `file_exists` work on the `--share` transcript. Claude tool names are mapped (Skill→skill, Read→view, Grep→rg, Bash→bash). `llm` graders are judged by `claude -p` with three votes, so Claude and Copilot runs share one judge. `baseline` and mock graders are skipped.
- Output: `evals/results/<timestamp>-copilot/aggregate-result.json` in the shape of Claude's file, plus `agent`, `model`, `judgeModel` fields. Each run's answer, transcript and debug log are kept next to it.
