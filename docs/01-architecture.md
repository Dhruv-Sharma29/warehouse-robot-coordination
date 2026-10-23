# 01 — Architecture

## One simulation step

```text
 LayoutSpec + seed ──► sim/layout.py (shelves, aisles, highways, stations, parking)
                                │
 Scenario (orders, faults) ─────┤
                                ▼
 ┌──────────────────────────── sim/engine.py, one step ───────────────────────────────┐
 │ faults ─► order arrivals ─► goal events ─► assignment ─► planning ─► safety ─► move │
 │                              (pickup/drop)   │  ▲          │           │            │
 │                                              ▼  │          ▼           ▼            │
 │                         planners/policies.py   │   planners/whca.py  sim/safety.py  │
 │                         Hungarian on estimated │   rolling WHCA*:    cancels any     │
 │                         travel time; station   │   space-time A*,    vertex/swap/    │
 │                         = min estimated time   │   reservations      invalid move,   │
 │                                                │                     asserts none    │
 │   estimate = distance | heuristic | learned ───┘                                    │
 └──────────────────────────────────────────────────────────────────────────────────────┘
        │ trips (features at decision time, realised steps)            │ metrics, replay
        ▼                                                              ▼
 predictor/dataset.py ─► predictor/train.py ─► results/models/*.json   runner/experiment.py, viz/
```

The order of the phases is fixed in `Simulation.run()` (`sim/engine.py`). Everything downstream of
the seed is deterministic, which is what lets every comparison in [04](04-evaluation.md) be paired.

## The three rules that make the design worth writing down

**Rule 1 — collision-freedom never depends on the planner.** `sim/safety.py` sits between the
plans and the motion. It turns every invalid move into a wait, iterates to a fixed point because
cancellations cascade, and then *asserts* that the result has no vertex or edge-swap conflict
(`check()` raises `CollisionError`). A planner bug can therefore cost throughput, and shows up as
`safety_interventions`, but it cannot produce a collision that goes unnoticed. That separation is
why the router could be replaced mid-project ([08](08-implementation-notes.md) § 4) without
re-validating safety.

**Rule 2 — the learned model only estimates cost.** Every policy shares the same WHCA* router,
safety layer and order stream; policies differ only in the travel-time estimate behind job
assignment and station choice (`planners/policies.py`). The model never proposes a move. Reason:
the research question is about decision quality, and a collision guarantee that depended on a
regression model would be no guarantee at all. It also makes the comparison clean: one variable
changes.

**Rule 3 — held-out means a different layout family, decided before any data exists.** Training
families (`std-6x4`, `std-8x6`) and held-out families (`wide-10x5`, `long-7x8-2st`) differ in aisle
count, block length and station count (`sim/layout.py`). The split is by family and seed in
`predictor/dataset.py`, and a test checks that no held-out family reaches the training or
validation data ([03](03-estimators.md) § Splits).

## Rules of the world

- **Time and motion:** discrete steps; each robot waits or moves to a 4-neighbour.
- **Collisions:** vertex (two robots in one cell) and edge-swap (two robots exchanging cells) are
  forbidden. Following into a cell being vacated is allowed.
- **Jobs:** go to the pickup, then a station chosen at pickup time. Completion is the arrival at the station.
- **Faults:**
  - A blocked aisle segment closes each cell once it's unoccupied, then reopens.
  - A failed robot becomes an obstacle, and its job is re-queued.
  - A loaded robot cut off from every station holds position and retries.
  - Unreachable jobs are reported, never waited on forever.

The recovery rules and the tests that pin them are in [02](02-coordination.md) § Faults.

## Components

| Module | Lines | Owns |
| --- | --- | --- |
| `sim/layout.py` | 125 | Procedural layouts; the train / held-out / scaling family definitions |
| `sim/scenario.py` | 65 | Seeded Poisson orders with two demand hotspots, 10% urgent; seeded faults |
| `sim/grid.py` | 71 | 4-connectivity, BFS distances cached per target and invalidated by a version counter when the blocked set changes |
| `sim/engine.py` | 275 | The step loop, job and robot state, fault handling, stuck detection, metrics, replay frames |
| `sim/safety.py` | 63 | The cascading safety layer and the collision assertion |
| `planners/whca.py` | 152 | Reservation table, space-time A*, rolling and clear round modes |
| `planners/policies.py` | 96 | Hungarian assignment, station choice; distance / heuristic / learned cost |
| `predictor/features.py` | 43 | The 11 decision-time trip features |
| `predictor/model.py` | 94 | Ridge (closed form) and the PyTorch MLP; numpy-only inference |
| `predictor/dataset.py`, `train.py`, `aggregate.py` | 71 / 73 / 107 | Data collection, training and the on-policy round |
| `runner/experiment.py` | 184 | Paired comparisons, tuning, router ablation, scaling, statistics |
| `viz/export.py`, `viz/replay.html` | 47 / 72 | Two policies, one scenario, one self-contained HTML file |

Line counts are from `wc -l` on the committed sources.

## Robot state

`Robot.phase` in `sim/engine.py`:

| Phase | Meaning | Leaves when |
| --- | --- | --- |
| `idle` | No job, no parking goal | Assigned a job, or sent to the nearest free parking cell |
| `parking` | Driving to a parking cell | Assigned a job (parking robots are assignable) |
| `to_pickup` | Driving to the job's pickup | Arrives: trip recorded, phase becomes `need_station` |
| `need_station` | Holding the item, no station yet | `choose_station()` returns a reachable station; otherwise holds and retries next step |
| `to_station` | Driving to the chosen station | Arrives: job done, robot `idle` |
| `failed` | Fault injected | Never. The cell becomes an obstacle; the job (if any) is re-queued |

## Decisions

- **Rolling windowed cooperative A\*** (window 16, full round every 4 steps). Each robot replans
  around everyone's still-valid plans, so the next 4 executed steps always have a valid plan. Ablation
  vs "clear" rounds: 0 vs ~430 safety interventions per run, +24% throughput.
- **Safety layer independent of the planner.** It turns invalid moves into waits and asserts
  collision-freedom every step. A planner bug can cost throughput but never cause a collision.
- **Stations are pass-through cells on the highway.** The first layout put them in dead-end pockets,
  and a robot waiting at the pocket's exit deadlocked the robot inside.
- **The learned model only estimates cost** for assignment and station choice. Routing stays
  classical, so collision-freedom never depends on a model.
- **Numpy inference.** The MLP's weights are copied out after PyTorch training. Thousands of
  small predictions per run would otherwise be dominated by framework overhead.
- **Splits by layout family.** Training families and held-out families differ in geometry (aisle
  count, block length, station count). Held-out families never enter training or model selection.

Two qualifications on the first bullet, both from the results: the "0 interventions" figure is the
router ablation on training layouts (`results/summary/router_ablation.json`, 12 runs per mode).
On the held-out comparison the rolling router still needs the safety layer occasionally — mean
2.9–93.9 interventions per run depending on policy and load, with the distance policy the worst
(`results/summary/compare_heldout.json`). Collisions stayed at 0 in every run. See
[02](02-coordination.md) § Where "by construction" stops.

## Data flow outside the step loop

```text
predictor.dataset ──► results/data/{train,val,heldout}.npz      (distance policy, round 0)
predictor.train   ──► results/models/{ridge,mlp}.json, results/summary/predictor.json
runner.experiment tune-heuristic ──► results/summary/heuristic_tuning.json
runner.experiment compare        ──► results/raw/compare_heldout.jsonl ──► results/summary/compare_heldout.json
predictor.aggregate --round 1    ──► results/data_r1/, results/models/mlp_r1.json, results/summary/aggregate_r1.json
runner.experiment compare-aggregated ──► results/raw/compare_heldout-aggregated.jsonl + summary
runner.experiment scaling | router-ablation | compare-train ──► results/summary/*.json
viz.export        ──► results/replay/*.html                      (generated output)
```

Summaries are built from the saved raw rows by `summarize()` in `runner/experiment.py`, so the
statistics can be recomputed without re-simulating.

## Repo layout

```text
06-warehouse-robot-coordination/
├── SPEC.md, PLAN.md, README.md, start.md
├── pyproject.toml, uv.lock     # no runtime deps declared: numpy/scipy/torch come from the host
├── env/ENVIRONMENT.md          # host, Python and library versions the results were produced with
├── docs/                       # you are here
├── sim/                        # layout, scenario, grid, engine, safety
├── planners/                   # whca.py (router), policies.py (assignment + station choice)
├── predictor/                  # features, model, dataset, train, aggregate
├── runner/experiment.py        # every experiment mode
├── viz/                        # export.py + replay.html template
├── tests/                      # test_simulator.py (11), test_experiment.py (4)
└── results/
    ├── data/, data_r1/         # trip datasets (.npz + meta), round 0 and round 1
    ├── models/                 # ridge.json, mlp.json, mlp_r1.json (numpy weights)
    ├── raw/                    # one JSON row per (scenario, policy) run
    ├── summary/                # the numbers the docs quote
    ├── replay/                 # generated side-by-side HTML replays
    ├── superseded_clear_router/  # first-router results, kept as evidence, not reported
    └── *.log                   # console output of the runs
```

PLAN.md's target layout had `scenarios/` and per-policy subpackages under `planners/`; the code
folded both into single modules ([08](08-implementation-notes.md) § 6).
