# 06 — Roadmap

Milestones are PLAN.md's. The Progress table in PLAN.md (dated 2026-10-06) is the status of
record; PLAN.md's checkboxes were ticked on 2026-10-23 to match it (the optional remote-predictor item
was done the same day).

## Milestones

| # | Milestone | Acceptance (MUST) | Evidence | State |
| --- | --- | --- | --- | --- |
| M1 | Simulator correctness | Vertex + edge-swap detection tested; impossible jobs reported; seeded determinism test | `tests/test_simulator.py` | **Done** |
| M2 | Classical baseline | Space-time A* with reservations + priority; assignment; deadlock metric; fault recovery; scale 20 → 100 with planner time | `planners/`, `results/summary/router_ablation.json`, `results/summary/scaling.json` | **Done** |
| M3 | Data collection | Varied layouts / traffic / faults; split by layout before generation; automated leakage check | `results/data/*.meta.json`, `test_held_out_layouts_never_reach_training_data` | **Done** (~107k / 32k / 59k trips) |
| M4 | Learned prediction | Simple supervised model first; report error and move on | `results/summary/predictor.json` | **Done** (ridge + MLP, 3 seeds) |
| M5 | Planner integration | Predictions change assignment or edge costs; collision checking unchanged; paired comparison with equal observation access | `planners/policies.py`, `results/summary/compare_heldout.json` | **Done** (assignment + station choice) |
| M6 | Generalisation + demo | Unseen layouts, higher load, urgent jobs, blocked aisles, failed robots; side-by-side replay | 80 held-out scenarios with faults; `results/replay/*.html` | **Done** |
| — | Follow-up: on-policy aggregation | One round, same held-out scenarios, paired | `results/summary/aggregate_r1.json`, `compare_heldout-aggregated.json` | **Done**, negative |
| — | Optional systems extension | Serve the predictor remotely, inject latency/drops, deterministic fallback | — | **Done 2026-10-23** (`results/summary/remote_inference.json`) |

## PLAN.md definition of done, item by item

| Item | Where it is met |
| --- | --- |
| Simulator tests | 15 tests, `tests/` |
| Fair paired comparisons | [04](04-evaluation.md) § Design |
| Unseen-layout results | [04](04-evaluation.md) § Results: held-out layouts |
| Failure cases | Gridlock at 100 robots ([02](02-coordination.md) § Scaling); MLP stuck episodes at saturation; round-1 regression ([04](04-evaluation.md)) |
| Visualisation | `viz/`, `results/replay/` |
| Limitations section | README § Limitations; [04](04-evaluation.md) § What the numbers do not show |

## Next, if pursued

From the README and PLAN.md, in the order the evidence suggests:

1. **Learn the assignment objective directly** (e.g. estimated completion rate rather than trip
   time). The aggregation round says better trip-time estimates aren't the bottleneck.
2. **Learned congestion costs inside routing.** Currently the router uses static distances; the
   safety layer means this can be tried without touching the collision guarantee.
3. **A stronger MAPF method for 100+ robots** (the README names PIBT or rule-based traffic
   lanes). Prioritised WHCA* gridlocks at 100 ([02](02-coordination.md) § Scaling).
4. **Sweep fault severity.** One fault mix per scenario so far.
5. ~~**The optional systems extension.**~~ Done 2026-10-23. Next would be enough runs to settle
   whether a lossy service's batch-by-batch mixing really costs throughput ([04](04-evaluation.md)).
6. **Run the macOS path on a real Mac.** It is tested on Linux only (README).

Before any of these produces a headline, it needs fresh held-out seeds ([05](05-risks.md) § R4).
