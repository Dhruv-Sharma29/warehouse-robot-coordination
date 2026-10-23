# 07 — Learning checklist

Ordered by the milestone that forces each skill, with "done when" tied to something in this repo.

## M1 — Simulator correctness

| Skill | Why | Done when |
| --- | --- | --- |
| Discrete-time multi-agent conflict model (vertex, edge-swap, following) | Every later number rests on these definitions | You can say why following is allowed and swapping isn't, and point at `test_following_is_allowed_and_cancellations_cascade` |
| Fixed-point resolution of cascading cancellations | One cancelled move can invalidate the robot behind it | `sim/safety.py` loop explained without reading it |
| Seeded determinism end to end | Paired comparisons need identical scenarios across policies | `test_fixed_seed_reproduces_exactly` hashes replay frames; 240/240 shared rows identical across two comparison runs |
| BFS distance fields with cache invalidation | Distances are queried constantly; blocks change them | You can explain the `Grid.version` counter |

## M2 — Classical baseline

| Skill | Why | Done when |
| --- | --- | --- |
| Space-time A* with vertex and edge reservations | The core of cooperative pathfinding | `plan_path()` traced on a 3-cell corridor (`test_planner_avoids_reserved_cells_and_swaps`) |
| Windowed, rolling replanning | Clear vs rolling was the biggest single gain in the project | You can explain why `2 * replan_every <= window` is asserted |
| Prioritised planning and its failure mode | Gridlock at 100 robots | You can explain the stuck-first priority term and why it isn't enough at 100 |
| Linear assignment (Hungarian, `scipy.optimize.linear_sum_assignment`) | Job assignment; infeasible pairs need a sentinel cost | You can say why the candidate set is capped at `max(3 × robots, 10)` |
| Fault-recovery rules as tested invariants | "Impossible jobs terminate" is a spec item | The four fault tests in [02](02-coordination.md) § Faults |

## M3 / M4 — Data and prediction

| Skill | Why | Done when |
| --- | --- | --- |
| Group-wise splits (by layout family) | Seed splits within a family test interpolation, not generalisation | `predictor/dataset.py` `SPLITS` and the leakage test |
| Decision-time features only | No future information at decision time | You can justify each of the 11 features in [03](03-estimators.md) |
| Ridge in closed form, unpenalised intercept | A transparent baseline model | `fit_ridge` |
| Log-target regression, checkpoint selection on validation, seed variance | Heavy-tailed targets; 3 seeds show the spread | `results/summary/predictor.json` seeds 0–2 |
| Metrics beyond MAE (congested MAE, rank correlation of excess) | Assignment needs the ranking of slow trips | You can say why ridge barely moves MAE but cuts congested MAE by a third |
| Exporting weights for framework-free inference | Thousands of tiny calls per run | `TravelTimeModel.predict` and the round-trip test |

## M5 / M6 — Closed-loop evaluation

| Skill | Why | Done when |
| --- | --- | --- |
| Paired experimental design | Removes scenario variance from the comparison | You can explain why n = 40 paired beats 40 + 40 unpaired |
| t-intervals on paired differences; direction-aware win counts | The verdict is the interval, not the mean | `paired()` and `test_paired_better_respects_metric_direction` |
| Choosing the right baseline | Learned vs distance answers the wrong question | [04](04-evaluation.md) § Baselines |
| On-policy data aggregation (DAgger-style) | Testing the distribution-shift explanation | `predictor/aggregate.py`, and stating the negative result |
| Process-pool batch simulation | A 320-run comparison is one command (the README estimates ~1 min for `compare`) | `multiprocessing.Pool` in `runner/experiment.py` |
| Self-contained HTML replay (canvas, data inlined) | A demo that opens anywhere | `viz/export.py` replaces `/*DATA*/null` in the template |

## Interview talking points, mapped to what was built

| Point | Backed by |
| --- | --- |
| "The strong baseline mattered more than the model." | Queue term alone 373 → 565 jobs (`heuristic_tuning.json`); heuristic vs distance +245.7 jobs saturated |
| "The safety layer is independent of the planner, so I could swap routers without re-proving safety." | `sim/safety.py`; clear → rolling change, collisions 0 throughout |
| "Rolling replanning removed the safety interventions and gave +24% throughput." | `router_ablation.json`: 434 → 0 interventions, 605.9 → 748.5 jobs |
| "The model is more accurate on unseen layouts, but not more useful." | `predictor.json` vs `compare_heldout.json` |
| "I tested my own explanation for the null result and it was wrong." | `aggregate_r1.json`; round-1 −19.1 jobs saturated vs round 0 |
| "Prioritised planning gridlocks at 100 robots; compute doesn't." | `scaling.json`: p95 10 ms per step, 29 stuck at end |
| "I report a superseded result set instead of deleting it." | `results/superseded_clear_router/README.md` |
