# 02 — Coordination: router, safety layer, faults

The classical side of the project, and the part the learned model is measured against. PLAN.md's
first risk is "a weak baseline makes any learned method look good", so this is where the effort
went first, and where the biggest single improvement in the project came from (§ Clear vs rolling).

## Conflict model

Two conflicts are forbidden, and the same definitions are used by the planner
(`planners/whca.py`) and by the safety layer (`sim/safety.py`):

| Conflict | Definition | Allowed look-alike |
| --- | --- | --- |
| Vertex | Two robots in one cell at the same step | — |
| Edge-swap | Robot A goes `a→b` while robot B goes `b→a` in the same step | Following: A enters `b` as B leaves it for `c` |

Following is allowed because a line of robots down a one-wide aisle is the normal case in this
layout; robots execute plans exactly ([00](00-charter.md) § Out), so entering a cell as it is
vacated carries no collision risk in the model.

## The router: rolling windowed cooperative A*

`plan_path()` searches `(cell, time)` for `window = 16` steps against a reservation table that
holds vertex reservations `(cell, t)` and edge reservations `(from, to, t)`. The heuristic is the
true BFS distance on the current map (`Grid.dist_to`), so it is exact for a single robot and only
reservations make the search work.

Outcomes of one search:

| Case | Returned path |
| --- | --- |
| Goal reached and holdable to the window's end | Path to goal, then hold |
| Goal not reachable inside the window | Best partial path: the reachable state at the window's end closest to the goal |
| Goal unreachable on the map | Plans to hold the current cell |
| Boxed in (no state at the window's end reachable) | Deepest valid prefix, then hold — the code comment says "safety layer protects the rest" |

**Rounds.** Every `replan_every = 4` steps, and immediately after any change to the blocked set
or any safety cancellation (`full_replan` in `sim/engine.py`), all active robots replan in
priority order. Between rounds, robots that get a new goal replan alone around the current
reservations. `WhcaRouter.__init__` asserts `2 * replan_every <= window`, the condition under
which an old plan is still valid through the next round.

**Priority order** (`Simulation._priority`): robots with no progress for ≥ 30 steps first (longest
stuck first), then urgent jobs, then robots that are working, then a rotation by
`(id + t // replan_every)` so no robot is permanently last. The first term is the project's
deadlock *resolution* rule; the `stuck_episodes` metric (no progress toward the goal for 30 steps,
counted once per episode) is the *detection*.

### Clear vs rolling

| Mode | What a round does | Jobs | Safety interventions | Stuck episodes | Planner s / run |
| --- | --- | --- | --- | --- | --- |
| `clear` (first router) | Drop all reservations; replan from scratch in priority order; unplanned robots are obstacles for 2 steps | 605.9 | 434.1 | 29.9 | 1.08 |
| `rolling` (default) | Each robot releases only its own reservations and replans around everyone else's current plans | **748.5** | **0** | **14.4** | 0.86 |

`results/summary/router_ablation.json`: training families, saturated load, heuristic policy,
seeds 401–403 × 20/40 robots = 12 runs per mode. +23.5% jobs, which the README rounds to +24%.

Why rolling wins: in `clear` mode a robot planned early in a round sees the robots not yet
planned only as 2-step obstacles, so conflicts beyond those 2 steps are left for the safety layer
to cancel, and every cancellation sets `full_replan` and forces another round. In `rolling` mode each robot plans against
real plans that extend at least `window - replan_every` steps ahead.

Because this change landed after the first full pipeline run, every dataset, model, tuning and
comparison was redone on the rolling router; the first set is kept in
`results/superseded_clear_router/` ([08](08-implementation-notes.md) § 4).

### Where "by construction" stops

The `whca.py` docstring says rolling execution is "conflict-free by construction". That holds on
the ablation above (0 interventions), but not everywhere:

| Experiment | Mean safety interventions per run (rolling router) | Source |
| --- | --- | --- |
| Held-out, moderate, distance / heuristic / MLP | 60.8 / 3.9 / 2.9 | `results/summary/compare_heldout.json` |
| Held-out, saturated, distance / heuristic / MLP | 93.9 / 11.8 / 9.5 | same |
| Training families, any regime, heuristic | 0 | `results/summary/compare_train-families.json` |
| Scaling, 100 robots | 11.3 | `results/summary/scaling.json` |

The highest single run is 349 (`results/raw/compare_heldout.jsonl`). The boxed-in fallback in
`plan_path()` is the code path that hands work to the safety layer; which case dominates on
held-out layouts has not been instrumented. The claim the docs make is therefore the narrower
one the code enforces: **collisions are 0 in every run**, because `check()` raises otherwise;
interventions are a throughput cost and are reported as a metric.

## The safety layer

`resolve(cur, proposed, grid)`:

1. Cancel any move that is not to a 4-neighbour or enters a non-passable cell.
2. Loop until nothing changes: cancel both robots of any swap; for any cell claimed by more than
   one robot, keep the robot already standing there, else the lowest id, and cancel the rest.
3. `check()` the result and raise `CollisionError` on any vertex or swap conflict.

Step 2 must iterate: cancelling one robot turns it into a stationary occupant, which can
invalidate the robot following it. `test_following_is_allowed_and_cancellations_cascade` pins
exactly that case.

Important detail for reading the metrics: `metrics()["collisions"]` is the constant `0`, with the
comment "impossible by construction: sim.safety.resolve asserts it every step". The evidence for
zero collisions is that the assertion never fired across the runs, not a counter. Tests that
check it independently of the assertion: `test_checker_rejects_collisions` and
`test_no_robot_ever_enters_a_blocked_cell_or_a_failed_robot`, which re-checks the replay frames.

## Assignment and station choice

Shared by all policies (`Policy.assign`, `Policy.choose_station`):

- **Assignment:** Hungarian matching (`scipy.optimize.linear_sum_assignment`) of free robots
  (`idle` or `parking`) to reachable pending jobs on *estimated* time to pickup, minus
  `URGENT_BONUS = 40` steps for urgent jobs. The candidate set is capped at
  `max(3 × robots, 10)` jobs, oldest and urgent first, so per-step cost stays flat.
- **Station:** chosen at pickup time, the reachable station with the lowest estimated travel time.
- **Parking:** unassigned idle robots go to the nearest untaken passable parking cell.

Only the estimate differs between policies; see [03](03-estimators.md).

## Faults

Every experiment scenario gets the same fault mix from `with_faults()`: two blocked 3-cell
segments of picking aisles for 150 steps each, and one robot failure, all at seeded times.

| Rule (from `sim/engine.py`) | Test |
| --- | --- |
| A blocked segment closes each cell as soon as it is unoccupied and reopens after its duration; every robot replans | `test_no_robot_ever_enters_a_blocked_cell_or_a_failed_robot` |
| A failed robot stays where it stopped and becomes an obstacle; its job goes back to the queue (`requeued_jobs`) | `test_failed_robot_stays_put_and_its_job_is_requeued` |
| A job whose pickup is unreachable is skipped until reachable; still unreachable at the end ⇒ `impossible_jobs`, and the run ends normally | `test_unreachable_job_terminates_and_is_reported` |
| A loaded robot cut off from every station keeps its job, holds, and retries each step (`waiting_for_route_steps`) | `test_loaded_robot_cut_off_from_all_stations_waits_instead_of_crashing` |

The last row is a regression: on held-out layouts a block closed on both sides of a loaded robot
and station choice crashed ([08](08-implementation-notes.md) § 2).

## Scaling

XL layout (`xl-14x6`, used only here), saturated orders, tuned heuristic, seeds 501–503
(`results/summary/scaling.json`):

| Robots | Jobs / 1000 steps | Jobs per robot | Stuck episodes | Stuck at end | Safety interventions | Planner p95 per step |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | 358.3 | 17.9 | 0 | 0 | 0 | 1.3 ms |
| 50 | 810.3 | 16.2 | 1.3 | 0 | 0 | 5.5 ms |
| 100 | 1,158.7 | 11.6 | 141.7 | 29.3 | 11.3 | 10.0 ms |

Compute is not the limit at 100 robots; coordination is. In the README's words, "prioritised
planning starts to gridlock". The 30-step priority boost does not clear it: on average 29 of 100
robots end the run stuck. The README names PIBT or rule-based traffic lanes as the next step;
neither was built.
