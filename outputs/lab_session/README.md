# Lab session outputs

This folder receives the design reviews the agent produces during the lab session (lab §5.1), together with the evidence behind them: after the session, each of the day's run directories is copied here from `runs/` into a folder named by the date, without its `progress.log` (which git ignores) and without its `ui/` folder (the page's chat and email logs, which are not part of the review, `docs/DEMO_DAY_SCRIPT.md` "After the session"), so that each run keeps its `report.md`, `report.json`, `manifest.json`, `ledger.json`, the call logs and its checkpoints for `dra replay`, `dra explain` and `dra coverage`; until the session this folder is empty by design, and nothing here is produced in advance.

```
D=outputs/lab_session/<YYYY-MM-DD>; mkdir -p "$D"
rsync -a --exclude progress.log --exclude ui/ runs/<run_id> "$D/"     # once per run of the day
git add "$D" && git commit -m "Lab session outputs of <YYYY-MM-DD>" && git push
```

An empty `snapshots/` folder is not tracked by git, and a run's `text/` folder holds the text of SIT's document, so it stays out of any public snapshot (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "What is and is not in this directory").
