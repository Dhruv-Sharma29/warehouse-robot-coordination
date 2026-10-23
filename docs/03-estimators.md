# 03 — Cost estimators: distance, heuristic, learned

Every policy answers one question, many times per step: *how long will it take this robot to
get to that cell?* The answer feeds the Hungarian cost matrix and the station choice
([02](02-coordination.md) § Assignment). Nothing else differs between policies.

## The three estimators

| Policy | Estimate | Parameters | Source |
| --- | --- | --- | --- |
| `distance` | Shortest-path distance on the current map | none | `DistancePolicy` |
| `heuristic` | `dist + per_robot × robots_on_path + per_queued × heading_to_goal` | tuned: `per_robot = 2`, `per_queued = 6` | `HeuristicPolicy`, `results/summary/heuristic_tuning.json` |
| `learned-ridge` / `learned-mlp` | Predicted realised travel steps from 11 features | trained | `LearnedPolicy`, `results/models/*.json` |

The heuristic and the learned models read **the same feature dict** (`trip_features`), so they
have identical observation access — a fairness requirement in SPEC.md and PLAN.md M5. The
heuristic is a two-parameter model over two of those features; the learned models use all 11.

## Decision-time features

`predictor/features.py`. Only what a fleet manager knows at the moment of the decision: robot
positions, robots' current goals, the static map and the blocked cells. No future knowledge.

| Feature | Meaning |
| --- | --- |
| `dist` | Length of one static shortest path (ties broken by neighbour order) |
| `robots_on_path`, `robots_on_path_per_cell` | Other robots currently standing on that path; and per path cell |
| `robots_near_start`, `robots_near_goal` | Other robots within Manhattan distance 3 |
| `heading_near_goal` | Other robots whose goal is within Manhattan distance 2 of this goal |
| `heading_to_goal` | Other robots whose goal *is* this goal (the station-queue signal) |
| `goal_is_station` | 1 if the goal is a drop-off station |
| `narrow_frac` | Fraction of path cells with ≤ 2 free neighbours |
| `turns` | Direction changes along the path |
| `fleet_density` | Other active robots / free cells |

The label is the realised number of steps from the decision to arrival (`_end_trip` in
`sim/engine.py`). Parking trips are not recorded.

## Why the heuristic is a real baseline, not a strawman

The tuning grid (`results/summary/heuristic_tuning.json`): 4 × 4 values of
`per_robot ∈ {0, 1, 2, 4}` and `per_queued ∈ {0, 3, 6, 12}`, 16 scenarios per cell on
**training** families (seeds 401–402, 20/40 robots, both regimes). Mean jobs completed:

| `per_robot` \ `per_queued` | 0 | 3 | 6 | 12 |
| --- | --- | --- | --- | --- |
| 0 | 372.7 | 565.4 | 571.4 | 564.2 |
| 1 | 450.6 | 553.1 | 570.5 | 558.7 |
| 2 | 424.9 | 529.9 | **576.4** | 563.5 |
| 4 | 485.8 | 569.8 | 574.1 | 564.8 |

The queue term alone (`0,0 → 0,3`) moves throughput from 373 to 565. Once `per_queued > 0`, the
grid spans 529.9–576.4, so the chosen point is not a knife-edge. The tuning never touches held-out layouts.

## Splits

Decided by family and seed in `predictor/dataset.py` before any data is generated:

| Split | Families | Seeds | Trips | Use |
| --- | --- | --- | --- | --- |
| train | `std-6x4`, `std-8x6` | 1–6 | 106,769 | Fitting |
| val | `std-6x4`, `std-8x6` | 7–8 | 31,628 | Early stopping, MLP seed selection |
| heldout | `wide-10x5`, `long-7x8-2st` | 101–104 | 58,821 | Accuracy only |

Counts from `results/data/*.meta.json`. Each split crosses fleets 15/25/35, order rates 0.4/0.8
and faults on/off, 800 steps per run, all under the distance policy.
`test_held_out_layouts_never_reach_training_data` checks the `family` column of the saved arrays;
`test_held_out_families_differ_from_training_families` checks the family names and grid shapes.
The closed-loop evaluation uses different seeds again (201–210, [04](04-evaluation.md)).

## Models

| Model | Shape | Target | Training |
| --- | --- | --- | --- |
| ridge | Linear on standardised features, α = 1, unpenalised intercept | steps | Closed-form solve (`fit_ridge`) |
| MLP | 11 → 64 → 64 → 1, ReLU | `log(1 + steps)` | Adam, lr 2e-3, batch 256, 60 epochs, keep the epoch with the best validation MSE; 3 seeds, best validation loss is saved |

The log target compresses the long tail of congested trips so the loss is not dominated by the
worst queues. That is the design intent; no raw-target MLP was trained for comparison.

**Numpy inference.** After training, the MLP's weights are copied into plain arrays
(`TravelTimeModel`), and the simulator never calls PyTorch. The model is queried thousands of
times per run in small batches, where framework overhead would dominate. Saved models carry the
feature list and refuse to load against a different one; `test_saved_model_reloads_with_identical_predictions`
checks the round trip.

## Accuracy

`results/summary/predictor.json`, held-out layouts (58,821 trips). "Congested" means realised
time ≥ 1.5 × distance (20.3% of held-out trips). Rank correlation is between predicted and actual
*excess* over distance, i.e. whether the model knows which trips will be slow.

| Model | MAE | MAE, congested | Rank corr. of excess |
| --- | --- | --- | --- |
| distance | 5.71 | 23.83 | 0.19 |
| distance, calibrated (1.003·d + 3.66) | 6.47 | 20.26 | 0.07 |
| ridge | 5.77 | 15.95 | 0.52 |
| MLP, seeds 0 / 1 / 2 | 4.46 / 4.52 / 4.49 | 15.50 / 15.08 / 15.35 | 0.56 / 0.57 / 0.55 |

Seed 2 is the saved model (lowest validation loss). Relative to distance the MLP is 21–22% lower
MAE and 35–37% lower congested MAE. Ridge barely moves overall MAE but cuts congested MAE by a
third: it knows *which* trips are slow even where it is not more accurate on average.

PLAN.md M4 says to report prediction error **and move on**: it is not the headline metric. The
closed-loop result in [04](04-evaluation.md) is.

## On-policy data aggregation (round 1)

Round 0 trips come from the distance policy, so the model never saw the trips its own
assignments create. `predictor/aggregate.py` (described in its docstring as DAgger-style):

1. Collect trips with the round-0 MLP on the same train / val configs: 116,821 + 38,690 trips
   (`results/aggregate_r1.log`).
2. Retrain the MLP on rounds 0 + 1 (223,590 training trips), 3 seeds, selected on both rounds'
   validation data.
3. Measure accuracy on held-out trips made by the learned policy (74,277 trips) — collected only
   for this measurement, never trained on.

`results/summary/aggregate_r1.json`:

| On held-out trips made by the learned policy | MAE | MAE, congested | Rank corr. |
| --- | --- | --- | --- |
| distance | 4.29 | 16.01 | 0.27 |
| round-0 MLP | 3.63 | 10.05 | 0.54 |
| round-1 MLP | 3.61 | 9.99 | 0.56 |

The round-0 model was already as accurate on its own distribution as the retrained one. The
closed-loop consequence is in [04](04-evaluation.md) § Follow-up.
