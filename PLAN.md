# 06 — Warehouse robot coordination simulator: execution plan

Brief: [SPEC.md](SPEC.md). Research question:

> Does a learned travel-time/congestion predictor improve fleet throughput and tail delay over a strong reservation-based classical planner, on **unseen layouts**, with zero added collisions?

Simulation study only — not a DeepFleet reproduction or a real-robot safety claim.

## Progress (2026-10-06; checkboxes ticked 2026-10-23 to match)

| Milestone | State |
| --- | --- |
| M1 simulator correctness | **Done.** Vertex/edge-swap rules, cascading safety layer, determinism, fault recovery, termination (tests) |
| M2 classical baseline | **Done.** Rolling WHCA* + Hungarian assignment; deadlock/stuck metrics; ablation vs first router |
| M3 data collection | **Done.** ~107k/32k/59k trips; split by layout family before collection; leakage test |
| M4 learned prediction | **Done.** Ridge + PyTorch MLP (3 seeds); −21% MAE, −36% congested MAE on held-out layouts |
| M5 planner integration | **Done.** Learned cost in assignment and station choice; paired vs naive and tuned heuristic |
| M6 generalisation + demo | **Done.** 80 held-out scenarios with faults; scaling 20→100 robots; side-by-side HTML replays |
| Optional systems extension | Not done: needs project 01's serving endpoint |

**Result:** the learned predictor matches but doesn't significantly beat a tuned congestion
heuristic in closed loop (see README). Follow-up done: one round of on-policy data aggregation. No
accuracy gain, and saturated throughput was significantly worse than round 0. Next experiments, if
pursued: learn the assignment objective directly, learned costs inside routing, and a stronger MAPF
method for 100+ robots.

## Target layout

```text
06-warehouse-robot-coordination/
  sim/                 grid world, robots, jobs, faults, step function, collision checker
  scenarios/           layouts, order streams, fault schedules (all seeded, versioned)
  planners/
    baseline/          space-time A* with reservation table + priority; greedy/Hungarian assignment
    heuristic/         simple congestion-penalty heuristic
    learned/           planner that consumes predictor outputs
  predictor/           dataset builder, model (MLP/GBM first, GNN optional), training
  runner/              batch scenario runner → results/raw
  viz/                 browser replay of saved runs
  tests/  results/raw/  results/summary/  docs/
```

## Milestones

### M1 — Simulator correctness (1–2 weeks)
- [x] Discrete time steps; 4-connected moves + wait.
- [x] Explicit **vertex** and **edge-swap** collision detection (tests for both).
- [x] Jobs: pickup → drop-off; completion rules; impossible jobs reported, not hung.
- [x] Seeded determinism test: same seed → identical trajectory hash.

### M2 — Classical baseline (1–2 weeks)
- [x] Space-time A* with reservation table, priority ordering; assignment policy.
- [x] Deadlock detection + resolution rule; count deadlocks as a metric.
- [x] Blocked aisle → replan without corrupting reservations. Failed robot → documented recovery (occupancy kept as obstacle, jobs reassigned).
- [x] Scale 20 → 100 robots; record planner compute time.

### M3 — Data collection (1 week)
- [x] Generate trajectories over varied layouts/traffic/faults.
- [x] Split by **layout** and seed **before** generation; automated check that held-out layouts never appear in training data or caches.

### M4 — Learned prediction (1–2 weeks)
- [x] Target: route travel time or local congestion. Start with a simple supervised model. GNN only if simple model plateaus.
- [x] Report prediction error **and** move on — it's not the headline metric.

### M5 — Planner integration (1–2 weeks)
- [x] Predictions modify edge costs or assignment; collision checking unchanged.
- [x] Paired comparison (same layout, orders, fleet size, faults, seeds): baseline vs heuristic vs learned.
- [x] Equal observation access and comparable planning budget.

### M6 — Generalization + demo (1 week)
- [x] Unseen layouts, higher load, urgent jobs, blocked aisles, failed robots.
- [x] Side-by-side browser replay.
- [ ] Optional: serve predictor via 01 gateway; inject latency/drops; deterministic fallback. (Not done: [docs/06](docs/06-roadmap.md).)

## Metrics
Orders completed per interval · mean/p95 travel time · total path cost · collisions (must be 0) · deadlocks · urgent-job delay · planner compute time. Multiple seeds; report variability (e.g. mean ± CI over seeds).

## Risks
- A weak baseline makes any learned method look good. Spend real effort on M2 before M4.
- Learned costs can cause oscillation (everyone avoids the same "congested" aisle). Watch for it.

## Definition of done
- [x] Simulator tests · [x] fair paired comparisons · [x] unseen-layout results · [x] failure cases · [x] visualization · [x] limitations section (physics, sensing, traffic realism)
