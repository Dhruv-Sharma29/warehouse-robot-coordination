# 05 — Risks and failure modes

Two kinds of risk: **thesis risks** (the study runs but doesn't show what it claims) and
**delivery risks** (it doesn't get finished, or doesn't reproduce). The project is complete, so
most delivery risks are now history; they are kept with what actually happened.

## Thesis risks

### R1 — Overselling a null result *(high likelihood, fatal to credibility)*

The MLP has the best mean on most held-out metrics ([04](04-evaluation.md)). It is tempting to
lead with "learned planning: +6.4 jobs, −14 p95". Every one of those intervals includes zero.

**Detection:** read `vs_heuristic` in `results/summary/compare_heldout.json`, not the means.
No learned-vs-heuristic interval on held-out layouts excludes zero.

**Mitigation:** the README and [04](04-evaluation.md) state the verdict first ("does not
measurably beat a tuned two-parameter congestion heuristic") and give the intervals next to every
difference. The suggestive p95 result is reported with its count (28/40) *and* the fact that it
reverses at saturation.

### R2 — A weak baseline *(high likelihood in general; PLAN.md's first listed risk)*

Comparing learned vs distance would have produced a headline +80 jobs moderate / +249 saturated
for the MLP — almost all of which the heuristic gets too (+73.5 / +245.7).

**Mitigation:** the heuristic is tuned on training families over a 16-point grid
(`results/summary/heuristic_tuning.json`) and uses the same features as the model. The router
itself was strengthened before the final comparison: rolling rounds raised baseline throughput
23.5% (`results/summary/router_ablation.json`), and everything was re-run on it.

### R3 — Leakage between training and evaluation layouts *(medium)*

Trip data, cached distances or model selection touching held-out layouts would turn
"generalisation" into memorisation.

**Detection:** `test_held_out_layouts_never_reach_training_data` (family column of the saved
train/val arrays); `test_held_out_families_differ_from_training_families` (names and grid shapes).

**Mitigation:** splits by family and seed fixed in code before collection
([03](03-estimators.md) § Splits); MLP seed selection on validation (training families); heuristic
tuning on training families; distance caches are per-simulation (`Grid._cache`), so nothing is
shared across runs.

### R4 — Held-out reuse *(medium, realised once)*

The aggregation round was designed after seeing the held-out null result and evaluated on the
same 80 scenarios.

**Mitigation:** honest reporting rather than prevention — the follow-up came out negative, so the
reuse can't have inflated it. Any future positive follow-up needs fresh held-out seeds (the
families support any seed).

### R5 — "Zero collisions" read as a stronger claim than it is *(medium)*

`collisions` is the constant `0` in `metrics()`; the guarantee is the assertion in
`sim/safety.py`, inside a model with exact execution.

**Mitigation:** [02](02-coordination.md) § The safety layer says exactly this, and points at the
two tests that check collision-freedom from replay frames rather than the counter.
`safety_interventions` is reported as its own metric so a planner that leans on the safety
layer is visible (it was: ~434 per run with the first router).

### R6 — Oscillation: everyone avoids the same "congested" aisle *(PLAN.md's second risk)*

**What happened:** the learned cost never touches routing, so aisle-level oscillation can't
arise from it. Station-level herding is what the `heading_to_goal` feature and the heuristic's
`per_queued` term exist to counter. Not instrumented directly; the stuck-episode increase for
the MLP at saturation on training families (+6.45 [0.89, 12.01]) is the closest signal and is
reported.

### R7 — Fragile heuristic tuning *(low)*

If the tuned point were a knife-edge, the heuristic's win would be luck.

**Detection:** the grid. With any queue term the 12 cells span 529.9–576.4 jobs; the best is 576.4
([03](03-estimators.md)).

## Delivery risks

### R8 — Router quality hides behind the safety layer *(realised)*

The first router "worked": no collisions, plausible throughput. It needed ~434 safety
interventions per run on the ablation and 929–1,976 per run on the held-out comparison
(`results/superseded_clear_router/compare_heldout.json`).

**Mitigation, applied:** interventions became a reported metric; the rolling router replaced it;
data, models, tuning and comparisons were all redone. The superseded set is kept as evidence
([08](08-implementation-notes.md) § 4).

### R9 — Gridlock at 100 robots *(realised)*

`results/summary/scaling.json`: 29.3 robots stuck at end, 141.7 stuck episodes per run.

**Mitigation:** reported as a limit, not hidden; a stronger MAPF method is named as the next
step ([06](06-roadmap.md)). The policy comparison stays at 20–40 robots, where the router is not
the bottleneck.

### R10 — Environment drift *(medium)*

`pyproject.toml` declares no runtime dependencies on the main path: numpy, scipy, scikit-learn
and torch come from the host's system site-packages, recorded in `env/ENVIRONMENT.md`. Another
machine gets whatever versions it has.

**Mitigation:** the `standalone` extra pins lower bounds for a clean install; the macOS path
exists but, per the README, has not been run on a real Mac **[verify]**. Published numbers come
from the recorded host only.

## Claim hygiene

| Say | Don't say |
| --- | --- |
| "The learned predictor is 21–22% more accurate than distance on unseen layouts" | "Learning improves fleet throughput" |
| "No significant closed-loop gain over a tuned heuristic; one retraining round made saturated throughput significantly worse" | "Matches the heuristic" without the intervals |
| "0 collisions, enforced by an assertion in a simulator with exact execution" | "Collision-free fleet coordination" |
| "Near-linear scaling to 50 robots; gridlock at 100" | "Scales to 100 robots" |
| "Two held-out layout families" | "Generalises to unseen warehouses" |

## The question to have a real answer for

> "Your model is more accurate. Why doesn't it help?"

Because the decision only needs the *ranking* of options, and the heuristic already gets the
ranking mostly right: a queue term alone takes training-layout throughput from 373 to 565 jobs.
The model's extra accuracy is mostly on trips whose choice doesn't change. Retraining on its own
trips confirmed accuracy wasn't the bottleneck: round 1 was as accurate (MAE 3.61 vs 3.63 on
learned-policy trips) and no better in closed loop. The next experiment is to learn the decision
objective (e.g. completion rate) rather than trip time, or to put learned costs inside routing.
The first two sentences of that answer are an interpretation consistent with the results,
not a measured fact; the measured facts are the numbers.
