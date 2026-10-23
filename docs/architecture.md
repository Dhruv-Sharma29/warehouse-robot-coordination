# Architecture

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

## Rules

- **Time and motion:** discrete steps; each robot waits or moves to a 4-neighbour.
- **Collisions:** vertex (two robots in one cell) and edge-swap (two robots exchanging cells) are
  forbidden. Following into a cell being vacated is allowed.
- **Jobs:** go to the pickup, then a station chosen at pickup time. Completion is the arrival at the station.
- **Faults:**
  - A blocked aisle segment closes each cell once it's unoccupied, then reopens.
  - A failed robot becomes an obstacle, and its job is re-queued.
  - A loaded robot cut off from every station holds position and retries.
  - Unreachable jobs are reported, never waited on forever.

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
