# 08 — Implementation notes: where the code departs from the plan

PLAN.md and SPEC.md are the plan; this is where building it changed things, and why. Each entry
names the evidence. Nothing here changes the research question.

## Bugs found and fixed

### 1. Stations in dead-end pockets deadlocked the fleet

The first layout put drop-off stations in pockets cut into the bottom wall. A robot waiting at a
pocket's only exit blocked the robot inside from ever leaving. Stations are now pass-through
cells on the lower lane of the bottom highway (`sim/layout.py`, comment in `build()`).

### 2. A robot cut off from every station crashed station choice

On held-out layouts a blocked aisle segment can close on both sides of a loaded robot. Station
choice found no reachable station and crashed. Now `choose_station()` returns `None`, the robot
keeps its job, holds position, and retries each step, counted in `waiting_for_route_steps`.
Regression test: `test_loaded_robot_cut_off_from_all_stations_waits_instead_of_crashing`.

### 3. "Better" meant "larger" for every metric

`paired()` once counted a scenario as better whenever the difference was positive, which inverts
the counts for cycle times, urgent misses, stuck episodes and everything else where lower is
better. Fixed with `HIGHER_IS_BETTER`; regression test
`test_paired_better_respects_metric_direction`.

Traces of the bug remain in two console logs: `results/compare_heldout.log` and
`results/compare_train.log` show heuristic vs distance `cycle_mean` as 32 better / 8 worse
(held-out) and 17 / 3 (train), where the summary JSONs show 8 / 32 and 3 / 17. Means and
intervals are unaffected; only the counts flip. `summarize()` rebuilds a summary from the saved
raw rows without re-simulating, the summary JSONs carry the corrected counts, and
`results/compare_aggregated.log` (from the later run) shows them too. **The summary JSONs are
authoritative.**

## Corrections driven by a measurement

### 4. The first router was replaced, and every result was redone

The first WHCA* implementation used "clear" rounds: drop all reservations, replan in priority
order, treat unplanned robots as obstacles for 2 steps. It never collided (the safety layer saw
to that) but needed ~434 interventions per run on the ablation and 929–1,976 on the held-out
comparison. Rolling rounds removed them on the ablation and raised throughput 23.5%
(`results/summary/router_ablation.json`).

Because the router sits under every policy, the data was re-collected, both models retrained,
the heuristic re-tuned and the comparison re-run. The first set is in
`results/superseded_clear_router/`, whose README says: "Kept as evidence, not reported." Two
details worth knowing about it:

- The heuristic's tuned weights changed with the router: 4 / 3 under clear rounds
  (`results/superseded_clear_router/heuristic_tuning.json`), 2 / 6 under rolling.
- `router_ablation()` in `runner/experiment.py` still hard-codes the **old** weights 4 / 3 for
  both modes. The comparison between modes is fair (same weights on both sides), but the
  rolling-mode figure of 748.5 jobs is not the tuned-heuristic figure.

The superseded numbers are not used anywhere else in these docs.

### 5. "Conflict-free by construction" is narrower than the docstring

`planners/whca.py` says rolling execution is conflict-free by construction. Held-out comparison
runs still record safety interventions (mean up to 93.9 per run for the distance policy at
saturation; one run reaches 349). The boxed-in fallback in `plan_path()` hands those cases to the
safety layer. Collisions remain 0. [02](02-coordination.md) § Where "by construction" stops has
the table; the docstring was left as is.

## Departures from the plan, with reasons

### 6. Flatter package layout

PLAN.md's target layout had `scenarios/` (layouts, orders, fault schedules "all seeded,
versioned") and `planners/baseline/`, `planners/heuristic/`, `planners/learned/`. The code has
`sim/scenario.py` and `sim/layout.py` instead, and one `planners/policies.py` with three classes.
Scenarios are not stored as files: they are regenerated from a family name and a seed, and the
family definitions in `sim/layout.py` are the versioned artefact. The repo does not record why
the planner subpackages were folded; the three policies are a few lines each in one 96-line
module.

### 7. The learned cost changes assignment, not edge costs

PLAN.md M5 allowed either. Assignment and station choice were chosen so that routing, and
therefore the collision argument, never depends on a model ([01](01-architecture.md) Rule 2).
The README lists this as one of two reasons the measured advantage may be small.

### 8. No GBM, no GNN

PLAN.md: "MLP/GBM first, GNN optional … GNN only if simple model plateaus." Ridge and an MLP were
built. The aggregation round showed accuracy was not what limited closed-loop value, so a larger
model was not pursued.

### 9. Training on CPU, inference in numpy

SPEC.md suggested the GPU for training. `env/ENVIRONMENT.md`: the GPU was shared with other
long-running jobs at the time, and a model this size gains nothing from it. Inference was moved
out of PyTorch entirely ([03](03-estimators.md) § Models).

### 10. Deadlock handling is detection plus a priority boost

PLAN.md M2 asked for "deadlock detection + resolution rule". Detection is `stuck_episodes`
(30 steps without progress). Resolution is ordering: stuck robots plan first. There is no
explicit deadlock-breaking manoeuvre; at 100 robots it is not enough ([02](02-coordination.md) § Scaling).

### 11. No runtime dependencies in `pyproject.toml`

numpy, scipy, scikit-learn and torch come from the host's system site-packages (an NVIDIA aarch64
torch build), with versions recorded in `env/ENVIRONMENT.md`. The `standalone` extra exists for
other machines.

## Added beyond the plan

### 12. One round of on-policy data aggregation

Not in PLAN.md's milestones; added to test the distribution-shift explanation of the null
result. Negative ([04](04-evaluation.md) § Follow-up).

### 13. A training-family comparison

`compare-train` runs the same comparison on training-family layouts (40 scenarios), to check
whether the null result is a generalisation problem. It isn't ([04](04-evaluation.md)).

## Deferred, not dropped

| Item | Why deferred | Source |
| --- | --- | --- |
| Optional systems extension (remote predictor, latency, fallback) | Needs project 01's serving endpoint | PLAN.md Progress |
| Fault-severity sweep | Not run; one fault mix per scenario (2 blocked segments, 1 failure) | README § Limitations |
| More aggregation rounds | Round 1 gave no accuracy gain and worse throughput | README § Limitations |
| Stronger MAPF for 100+ robots (PIBT or traffic lanes) | Named as the next step, not started | README § Scaling |
| macOS run on real hardware | No Mac used yet; code paths tested on Linux only | README § macOS |
