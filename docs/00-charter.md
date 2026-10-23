# 00 — Charter

## The problem

A robot fleet in a warehouse spends its time on two decisions: *which robot takes which job*, and
*how robots move without colliding*. The classical answer to the first is to estimate travel cost
by shortest-path distance and match robots to jobs. That estimate is blind to congestion: it
sends every loaded robot to the nearest drop-off station and builds a queue there.

The obvious ML pitch is "learn the travel time and the fleet gets faster". The question this
project actually asks is narrower and harder to fake:

> Does a learned travel-time/congestion predictor improve fleet throughput and tail delay over a
> **strong** reservation-based classical planner, on **unseen layouts**, with zero added
> collisions? (PLAN.md)

"Strong" is the load-bearing word. A learned model compared against naive distance will always
look good. Compared against a tuned congestion heuristic with the same inputs, it may not — and
in this project it doesn't ([04](04-evaluation.md)).

## What it does

**Input:** a layout family and seed, a fleet size, an order rate, and a seeded fault schedule
(blocked aisles, a robot failure). Everything derives from seeds.

**Output:**
1. A deterministic 1,000-step simulation with a collision-free multi-robot router and a
   per-run metrics row (jobs, cycle times, urgent misses, stuck episodes, safety interventions,
   planner time).
2. Paired comparisons of assignment policies across scenarios, with 95% intervals and win/loss
   counts (`results/summary/`).
3. A trained travel-time predictor and its accuracy on held-out layouts.
4. Self-contained HTML replays of two policies on the same scenario.

## Scope

### In
- A 2D 4-connected grid warehouse: shelves, picking aisles, highways, pass-through stations,
  parking ([01](01-architecture.md)).
- Explicit vertex and edge-swap collision rules, enforced by a safety layer that asserts them.
- Rolling windowed cooperative A* (WHCA*) routing; Hungarian assignment; nearest-by-estimate
  station choice ([02](02-coordination.md)).
- Faults: blocked aisle segments, robot failures, unreachable jobs, robots cut off from stations.
- Three cost estimators behind one interface: distance, tuned heuristic, learned (ridge, MLP)
  ([03](03-estimators.md)).
- Fleets of 20–40 robots for the comparison; 20–100 for scaling.

### Out (deliberately, not from running out of time)
- **Physics, sensing, stochastic execution.** Robots execute plans exactly. Adding noise would
  test robustness of the router, which is a different question from whether a better cost
  estimate helps assignment.
- **Learned routing or end-to-end RL.** SPEC.md keeps RL out of the first version. Keeping the
  model out of the motion layer is also what keeps the collision guarantee independent of it
  ([01](01-architecture.md) Rule 2).
- **A GNN.** PLAN.md made it conditional on the simple model plateauing. The evidence points the
  other way: accuracy improved and closed-loop value didn't ([04](04-evaluation.md) § Follow-up),
  so a bigger model attacks the wrong bottleneck.
- **3D simulators, ROS2, hardware.** Listed in SPEC.md as later extensions with their own
  compatibility work.
- **Real warehouse data.** None is available; layouts, orders and faults are synthetic.

### Why this scoping holds up in an interview
Every narrowing serves one thing: a comparison where **only the cost estimate changes**. Same
router, same safety layer, same orders, same faults, same seeds — so a difference in jobs
completed can only come from the estimate. Widen the scope (learned routing, stochastic motion)
and a null result could be blamed on a dozen things; here it can't.

## Non-goals

- Reproducing any production fleet system. SPEC.md names one as motivation; this is a
  simulation study, not a reproduction.
- A real-robot safety claim. "0 collisions" means 0 in this model of the world.
- State-of-the-art MAPF. WHCA* with prioritised planning is the classical baseline, chosen to be
  strong enough to make the comparison fair, not to be the best planner available.

## Success criteria

| # | Criterion | How it's checked | State |
| --- | --- | --- | --- |
| S1 | Vertex and edge-swap collisions are detected explicitly | `test_vertex_conflict_is_cancelled`, `test_edge_swap_is_cancelled`, `test_checker_rejects_collisions` | Met |
| S2 | Zero collisions in every run | `check()` asserts each step; `collisions` = 0 in all 800 rows of `results/raw/*.jsonl` | Met |
| S3 | A fixed seed reproduces the same scenario | `test_fixed_seed_reproduces_exactly` (metrics + SHA-256 of replay frames) | Met |
| S4 | Impossible jobs terminate and are reported | `test_unreachable_job_terminates_and_is_reported` | Met |
| S5 | Blocked aisle and robot failure follow documented recovery rules | Fault tests in [02](02-coordination.md) § Faults | Met |
| S6 | Held-out layouts never enter training data | `test_held_out_layouts_never_reach_training_data` | Met |
| S7 | A strong classical baseline: tuned heuristic, not just distance | `results/summary/heuristic_tuning.json`; heuristic vs distance +245.7 jobs saturated | Met |
| S8 | Paired closed-loop comparison on unseen layouts with intervals | `results/summary/compare_heldout.json`, 80 scenarios | Met |
| S9 | Scaling to ~100 robots with planner time recorded | `results/summary/scaling.json` | Met, with gridlock at 100 reported |
| S10 | Side-by-side visualisation | `results/replay/*.html` | Met |
| S11 | Optional: remote inference with injected latency and a safe fallback | `runner/remote.py` → `results/summary/remote_inference.json`; `tests/test_remote.py` | Met (own HTTP service; project 01's gateway serves only chat completions) |

`uv run pytest` runs 15 tests; all pass.

## The honest risk to the thesis

The thesis was that a learned predictor helps. The result is that it is **more accurate but
not more useful**: 21–22% lower MAE than distance on held-out layouts (35–37% lower on congested
trips), no significant closed-loop gain over the
tuned heuristic, and a retraining round that made saturated throughput significantly worse.
The risk was never that the model would fail to learn; it was that accuracy would not translate
into decisions. The project is built so that this outcome is measurable and reportable rather
than hidden, and [05](05-risks.md) § R1 is about not overselling what remains.
