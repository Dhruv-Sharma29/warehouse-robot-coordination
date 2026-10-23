# 04 — Evaluation

## The question

From PLAN.md:

> Does a learned travel-time/congestion predictor improve fleet throughput and tail delay over a
> strong reservation-based classical planner, on **unseen layouts**, with zero added collisions?

The comparison that decides it is **learned vs tuned heuristic**, not learned vs distance.
Beating naive distance is easy for anything queue-aware; the heuristic isolates what a trained
model adds beyond a two-parameter congestion rule with the same inputs ([03](03-estimators.md)).

## Baselines

| ID | Policy | Isolates |
| --- | --- | --- |
| B0 | `distance` | The floor: congestion-blind assignment and nearest-station choice |
| B1 | `heuristic` (tuned 2 / 6 on training families) | **Does learning add anything beyond a queue-aware rule?** |
| L1 | `learned-ridge` | A transparent learned model |
| L2 | `learned-mlp` (round 0) | The main learned model |
| L3 | `learned-mlp_r1` | L2 retrained with on-policy data (follow-up only) |

All share the router, safety layer, order stream and faults; only the estimate differs.

## Design

`runner/experiment.py`. Every policy runs the identical scenario — layout, orders, fleet, faults,
seed — so every difference is paired.

| Set | Families | Seeds | Fleets | Regimes | Scenarios | Rows |
| --- | --- | --- | --- | --- | --- | --- |
| Held-out (`compare`) | `wide-10x5`, `long-7x8-2st` | 201–210 | 20, 40 | moderate, saturated | 80 | 320 |
| Training families (`compare-train`) | `std-6x4`, `std-8x6` | 301–305 | 20, 40 | both | 40 | 160 |
| Held-out, aggregated (`compare-aggregated`) | same as held-out | 201–210 | 20, 40 | both | 80 | 320 |

Order rates per step: moderate 0.30 (20 robots) / 0.50 (40 robots); saturated 1.0 for both.
1,000 steps per run, faults in every run ([02](02-coordination.md) § Faults).

## Metrics

Per run, from `Simulation.metrics()`:

| Metric | Definition | Better |
| --- | --- | --- |
| `jobs_completed` | Jobs delivered to a station within the horizon | higher |
| `cycle_mean`, `cycle_p95` | Order creation → delivery, completed jobs only | lower |
| `urgent_missed` | Urgent jobs due within the horizon that were late or not done | lower |
| `moves` | Robot-steps spent moving (a path-cost proxy) | lower |
| `safety_interventions` | Moves the safety layer cancelled | lower |
| `stuck_episodes` | Episodes of 30 steps with no progress toward the goal | lower |
| `planner_s` | Wall-clock time in the planner per run | lower |
| `collisions` | Constant 0, guaranteed by the assertion ([02](02-coordination.md) § The safety layer) | — |

Note that `cycle_*` only counts completed jobs, so a policy that completes more jobs, including
older ones, can show a *higher* mean cycle time while being better. That is visible below: the
heuristic beats distance on jobs but has a higher moderate-load mean cycle time.

## Statistics

`paired()`: per-scenario difference vs a base policy; mean; 95% t-interval from a hard-coded
quantile table (`T95`: df 9/19/39/79; 1.96 otherwise); and better / worse / tie counts that
respect each metric's direction. Results are split by regime, so n = 40 per regime on held-out
and n = 20 on training families. An interval that includes 0 is reported as "not significant";
no multiple-comparison correction is applied across the 8 metrics × 2 regimes.

`test_paired_better_respects_metric_direction` exists because "better" once meant "larger" for
every metric ([08](08-implementation-notes.md) § 3).

## Results: held-out layouts

`results/summary/compare_heldout.json`, means per run:

| Policy | Jobs, mod. | Jobs, sat. | p95 cycle, mod. | p95 cycle, sat. | Urgent missed, mod. / sat. | Stuck, mod. / sat. |
| --- | --- | --- | --- | --- | --- | --- |
| distance | 298.8 | 361.6 | 74.4 | 352.5 | 6.58 / 25.1 | 24.7 / 62.4 |
| heuristic | 372.3 | 607.3 | 80.5 | 381.1 | 0.40 / 2.58 | 31.2 / 54.0 |
| learned-ridge | 375.0 | 603.3 | 66.4 | 396.1 | 0.23 / 2.35 | 25.4 / 60.4 |
| **learned-mlp** | **378.7** | **611.0** | **66.2** | 396.9 | **0.17 / 1.77** | 25.3 / 59.4 |

Paired differences, 95% CI, better/worse counts out of 40:

| Comparison | Jobs, moderate | Jobs, saturated | p95 cycle, moderate | p95 cycle, saturated |
| --- | --- | --- | --- | --- |
| heuristic vs distance | **+73.5** [29.8, 117.3], 16/11 | **+245.7** [164.6, 326.8], 36/4 | +6.0 [−23.7, 35.8] | +28.7 [−23.7, 81.0] |
| MLP vs heuristic | +6.4 [−0.4, 13.3], 19/9 | +3.7 [−12.9, 20.3], 24/16 | −14.3 [−30.8, 2.3], 28/7 | +15.7 [−3.1, 34.6], 20/19 |
| ridge vs heuristic | +2.7 [−10.3, 15.7], 24/7 | −4.0 [−20.0, 12.0], 22/16 | −14.1 [−33.5, 5.3], 23/10 | +15.0 [−4.3, 34.2], 18/19 |

**Verdict.** Being queue-aware at all is worth +74 to +246 jobs per run on unseen layouts. The
learned models add nothing significant on top of the tuned heuristic. The MLP's moderate-load
p95 advantage is suggestive (better in 28 of 40 scenarios) but its interval includes zero, and at
saturation the sign flips (also not significant). Urgent misses are lowest with the MLP, but the
difference to the heuristic is not significant either (−0.8 [−2.5, 0.9] saturated).

Across all 8 metrics and both regimes, no learned-vs-heuristic difference on held-out layouts
has an interval that excludes zero. The one measurable cost of the learned policy is compute:
`planner_s` +0.06 s per run vs distance at moderate load [0.01, 0.11], +0.08 [0.02, 0.13] at
saturation.

## Results: training-family layouts

`results/summary/compare_train-families.json`, 40 scenarios (n = 20 per regime).

| MLP vs heuristic | Moderate | Saturated |
| --- | --- | --- |
| Jobs | +0.75 [−1.22, 2.72] | −7.6 [−21.56, 6.36] |
| Mean cycle | **−1.08 [−1.56, −0.59]** | not significant |
| Moves | not significant | **−600 [−957, −244]** |
| Stuck episodes | not significant | **+6.45 [0.89, 12.01]** (worse) |

On the layouts it was trained on, the MLP makes slightly shorter cycles and fewer moves, but it
completes no more jobs and gets stuck more often at saturation. Ridge shows the same pattern at
moderate load (mean cycle, p95 cycle and moves significantly lower, jobs not different).
In-distribution layouts do not turn the small accuracy gains into throughput.

## Follow-up: retraining on the model's own trips

Hypothesis: the null result is distribution shift (round-0 data came from the distance policy).
`results/summary/compare_heldout-aggregated.json` re-runs the same 80 held-out scenarios with the
round-1 model. The three earlier policies reproduced exactly: all 240 shared rows are identical
to `results/raw/compare_heldout.jsonl` except the timing fields (checked by diffing the two raw
files), so this comparison is still paired.

| Round-1 MLP, paired difference (95% CI) | Jobs, moderate | Jobs, saturated | Urgent missed, saturated |
| --- | --- | --- | --- |
| vs tuned heuristic | −2.0 [−14.8, 10.9] | −15.4 [−34.8, 4.0] | +1.3 [−1.4, 4.0] |
| vs round-0 MLP | −8.4 [−18.8, 2.0] | **−19.1 [−34.1, −4.1]** | **+2.1 [0.4, 3.8]** |

The "vs round-0" row is not in the summary JSON (it only stores `vs_distance` and
`vs_heuristic`); it is `paired(rows, "learned-mlp_r1", metric, base="learned-mlp")` over
`results/raw/compare_heldout-aggregated.jsonl`.

**Conclusion.** Distribution shift was not the bottleneck: round-0 was already as accurate on
its own trips ([03](03-estimators.md) § On-policy data aggregation), and the retrained model is
significantly *worse* at saturation. The limit is the decision value of a better estimate beyond
what the queue-aware rule captures.

## Side-by-side replays

Generated by `viz/export.py` with its defaults (`wide-10x5`, seed 205, 40 robots, saturated):

| File | Left vs right | Jobs |
| --- | --- | --- |
| `results/replay/distance-vs-heuristic.html` | distance vs heuristic | 277 vs 862 |
| `results/replay/heuristic-vs-learned.html` | heuristic vs learned-mlp | 862 vs 852 |

Read from the data embedded in each file. These are one scenario each, chosen as a demo — use
them to *see* station queues forming under the distance policy, not as evidence.

## Follow-up: local vs remote inference (2026-10-23)

SPEC.md's optional systems extension: the MLP served by `predictor/serve.py` (standard-library HTTP),
called by `planners/remote.py` with a 100 ms budget per batch; on a timeout, a dropped connection
or a bad reply that batch falls back to the tuned heuristic, and a circuit breaker (3 failures in a
row, then 50 calls skipped, counted in calls so it is deterministic) stops hammering a dead service.
`python -m runner.remote` → `results/summary/remote_inference.json`. Simulated systems behaviour,
not real robot offloading.

| Condition (20 paired held-out runs: 2 families × moderate/saturated × 5 seeds, 20 robots) | Jobs (mean) | Fallback share | Wall per run | Δ jobs vs local, 95% CI |
| --- | --- | --- | --- | --- |
| Local MLP (in process) | 420.15 | — | 1.13 s | — |
| Remote, healthy | 420.15 | 0 % | 1.68 s | 0.00 (identical in all 20) |
| Remote, every reply 250 ms late (100 ms budget) | 419.55 | 100 % | 5.77 s | −0.60 [−6.98, 5.78] (equals the heuristic exactly) |
| Remote, 20 % of connections dropped | 406.45 | 38 % | 1.55 s | −13.70 [−28.62, 1.22], 5 better / 13 worse |
| Heuristic alone (the fallback) | 419.55 | — | 1.09 s | −0.60 [−6.98, 5.78] |

The fallback is safe: 0 collisions in every condition, and a dead service degrades exactly to the
heuristic. A healthy service reproduces the local model bit for bit, at about 0.55 s extra per run
(HTTP round trips). A lossy service mixes the two estimators batch by batch, and the circuit breaker
raises the fallback share to 38 % for a 20 % drop rate. It lost 13.7 jobs on average against local
and 13.1 against the heuristic, with the losses in a few runs; neither interval excludes zero on 20
runs, so "mixing estimators hurts" is a lead, not a result. Tests: `tests/test_remote.py`.

## What the numbers do not show

- **Not a real warehouse.** Exact execution, no localisation error, synthetic orders and faults.
  Two held-out families test geometric generalisation only.
- **One fault mix.** Two blocked segments and one robot failure per run; severity not swept.
- **Held-out reuse.** The aggregation follow-up was motivated by the held-out result and then
  evaluated on the same 80 held-out scenarios. Its result was negative, so the reuse cannot have
  flattered it, but a positive result here would have needed fresh seeds.
- **Learned cost only in assignment and station choice.** Routing still uses static distances; a
  learned cost inside the router is untested.
