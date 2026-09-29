# M3 dogfood (step 9)

AEW with a headless model Lead, against raw OpenCode, on six small but real tasks. The report is
`docs/implementation/m3-dogfood-report.md`. The rubric was fixed before any paid run: `rubric.md`.

| File | What |
|---|---|
| `dogfood.py` | the driver: `selfcheck`, `run <task> --mode aew\|raw --model provider/model#effort`, `setup` |
| `headless.py` | a headless OpenCode session (the Lead, or the raw baseline), built on the production adapter |
| `hidden.py` | the hidden tests: never inside a repository a model works in |
| `fixture/base` | the `ledger` project (a small CSV ledger with a CLI and tests) |
| `fixture/overlays/<task>` | each task's starting point (the planted bugs) |
| `fixture/seeded/T5` | T5's seeded first implementation |
| `fixture/reference` | reference solutions, used only by `selfcheck` |
| `rubric.md` | the pre-registered rubric and hypotheses |
| `results.jsonl` | one record (`aew/dogfood-run/v1`) per paid run, whatever its outcome |

Every run works in a scratch directory under the system temp directory (`aew-dogfood/<task>-<mode>-<stamp>`), never
in the AEW checkout. It records whether the checkout stayed untouched, and whether any AEW credential or the provider
key reached a file.

Reproduce, from the AEW checkout, with the provider key set in the environment (only its name is ever configured):

```
python eval/m3/dogfood/dogfood.py selfcheck
python eval/m3/dogfood/dogfood.py run T1 --mode aew --model openai/gpt-5.6-luna#medium
python eval/m3/dogfood/dogfood.py run T1 --mode raw --model openai/gpt-5.6-luna#medium
```

Run it from Git Bash (`SHELL` set) to give the agents bash, as recorded in `agent_shell`.
