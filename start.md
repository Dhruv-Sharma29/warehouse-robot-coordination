# Start here

A guide to running the simulator and the experiments, and to reading what they produce. The
[README](README.md) states the result; [docs/](docs/README.md) is the design record; this file
gets you from a clone to numbers you can check.

Everything runs on CPU. No credentials, services or GPU are involved, so there is no RUNBOOK.

---

## 1. Install

On the machine the results were produced on (numpy, scipy, scikit-learn and torch come from the
system Python; versions in `env/ENVIRONMENT.md`):

```bash
uv venv --system-site-packages --python /usr/bin/python3 && uv sync
```

Anywhere else, including macOS, install the libraries into the venv instead:

```bash
uv sync --extra standalone
```

`pyproject.toml` deliberately declares no runtime dependencies on the main path; the `standalone`
extra gives lower bounds only, so your versions may differ from the recorded ones.

## 2. Run the tests

```bash
uv run pytest
```

15 tests: collision rules, the cascading safety layer, planner reservations, seeded determinism,
fault recovery, termination of impossible jobs, layout-family separation, paired statistics,
the leakage check on the committed datasets, and model save/load. Two of them skip with a message
("run python -m predictor.dataset first", "train first") if `results/data/` or
`results/models/` is missing.

## 3. See it work, without the experiment runs

The committed replays need nothing but a browser:

```text
results/replay/distance-vs-heuristic.html   distance vs tuned heuristic, 277 vs 862 jobs
results/replay/heuristic-vs-learned.html    tuned heuristic vs learned MLP, 862 vs 852 jobs
```

Both are `wide-10x5` (a held-out layout family), seed 205, 40 robots, saturated orders. Watch the
bottom highway in the first one: under the distance policy every loaded robot heads for the
nearest station and the queues form there. Blue robots are waiting, green moved in the last
step, red are failed; the red squares are blocked aisle segments.

To regenerate one (two 1,000-step simulations, a few seconds on CPU):

```bash
uv run python -m viz.export --out /tmp/demo.html
```

With the defaults it prints `{'distance': 277, 'heuristic': 862}`, the same numbers as the
committed file. `--left` / `--right` take `distance`, `heuristic`, `learned-mlp`,
`learned-ridge` or `learned-mlp_r1`; `--family`, `--seed`, `--robots` and `--regime` pick the scenario.

## 4. Reproduce the results

**These commands overwrite the committed files under `results/`.** Run them in a scratch clone
if you want to diff against the published numbers. Order matters: later steps read earlier
outputs.

```bash
uv run python -m runner.experiment router-ablation  # clear vs rolling WHCA*      -> summary/router_ablation.json
uv run python -m predictor.dataset                  # trips, distance policy      -> results/data/
uv run python -m predictor.train                    # ridge + 3 MLP seeds         -> results/models/, summary/predictor.json
uv run python -m runner.experiment tune-heuristic   # 16-point grid, train layouts -> summary/heuristic_tuning.json
uv run python -m runner.experiment compare          # 80 held-out scenarios x 4   -> raw/ + summary/compare_heldout.json
uv run python -m runner.experiment compare-train    # 40 training-family scenarios -> summary/compare_train-families.json
uv run python -m predictor.aggregate --round 1      # on-policy round             -> results/data_r1/, models/mlp_r1.json
uv run python -m runner.experiment compare-aggregated
uv run python -m runner.experiment scaling          # 20/50/100 robots, XL layout -> summary/scaling.json
```

`runner.experiment` and `predictor.aggregate` default to `--workers 10`, `predictor.dataset` to
`--workers 8`. The README's timings (~40 s for the dataset, ~1 min for `compare`) are for the
recorded host **[verify]** on yours.

`predictor.train` takes no arguments: even `--help` starts a training run and rewrites its outputs.

## 5. Read the output

Every comparison summary has the same shape:

```text
compare_heldout.json
├── label, scenarios, heuristic_params
└── by_regime
    ├── moderate | saturated
    │   └── distance | heuristic | learned-mlp | learned-ridge
    │       ├── mean           {jobs_completed, cycle_mean, cycle_p95, urgent_missed, moves,
    │       │                   safety_interventions, stuck_episodes, planner_s}
    │       ├── vs_distance    {metric: {n, mean_diff, ci95, better, worse, ties}}
    │       └── vs_heuristic   (learned policies only) same shape
```

What to look at, in order:

1. `vs_heuristic` for `learned-mlp`, both regimes. This is the comparison the claim rests on. If
   `ci95` contains 0, the difference is not significant at 95%.
2. `better` / `worse` already respect each metric's direction (for `cycle_p95`, better = lower).
3. `vs_distance` for `heuristic`. This is how much being queue-aware is worth on its own.
4. `safety_interventions`. Not a collision count; moves the safety layer cancelled. Nonzero
   means the planner leaned on it ([docs/02](docs/02-coordination.md)).

Per-run rows are in `results/raw/compare_*.jsonl`, one line per (scenario, policy), with more
fields than the summary (`requeued_jobs`, `impossible_jobs`, `robots_stuck_at_end`, `astar_calls`).

Ignore `results/superseded_clear_router/`: results from the first router, kept as evidence and
not reported ([docs/08](docs/08-implementation-notes.md) § 4).

## 6. Where to read next

| If you want | Read |
| --- | --- |
| The answer and its caveats | [README](README.md), then [docs/04](docs/04-evaluation.md) |
| Why the classical baseline is strong | [docs/02](docs/02-coordination.md), [docs/03](docs/03-estimators.md) § Why the heuristic is a real baseline |
| What could be wrong with the claim | [docs/05](docs/05-risks.md) |
| What changed during the build | [docs/08](docs/08-implementation-notes.md) |

## 7. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `ModuleNotFoundError: numpy` (or `scipy`, `torch`) | The venv has no system site-packages and no `standalone` extra: re-run step 1 with one of the two |
| `AssertionError: more robots than parking cells` | Fleet too large for the layout's parking cells; the scaling runs use `xl-14x6`, which `sim/layout.py` defines for "room for 100+ robots" |
| `ValueError: model was trained on a different feature list` | `results/models/*.json` predates a change to `FEATURES` in `predictor/features.py`; retrain (step 4) |
| `CollisionError` | A planner or engine change produced a conflict the safety layer could not cancel. This is a bug, not a flaky test |
| Two tests skipped | `results/data/` or `results/models/` is missing; run `predictor.dataset` and `predictor.train` |
| Timings differ from the README | Expected: published timings are from the host in `env/ENVIRONMENT.md`; the README says Mac timings are not comparable |
