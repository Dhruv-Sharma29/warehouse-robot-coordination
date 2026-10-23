# 06 — Warehouse robot coordination simulator

**Build sixth in the general portfolio order.** Move it earlier for Amazon Robotics or robotics-focused ML applications.

## Objective

Build a simulated warehouse where robot routing and job assignment adapt to congestion, blocked aisles, urgent orders, and robot failures. Test whether learned travel-time or congestion predictions improve a strong classical baseline.

## Why this fits Amazon and Microsoft

[Amazon DeepFleet](https://www.amazon.science/blog/amazon-builds-first-foundation-model-for-multirobot-coordination/) predicts mobile-robot traffic and supports fleet coordination. [Microsoft's physical AI systems research](https://www.microsoft.com/en-us/research/blog/offloaded-inference-for-real-world-physical-ai-robotics/) explores inference placement across robots, edge, and cloud.

Amazon is the clearest direct match. A later latency/offloading experiment can strengthen the systems connection to Microsoft. This is a simulation study, not a reproduction of DeepFleet or proof of real-world robot safety.

2028+ assessment: fleet coordination, learned planning support, and physical AI infrastructure are promising directions, with greater implementation/research uncertainty than the earlier projects.

## Minimum viable scope

- A deterministic 2D grid warehouse simulator.
- Around 20 robots initially; test larger fleets up to roughly 100 when feasible.
- Pickup/drop-off jobs, obstacle maps, occupancy, and explicit collision rules.
- Classical routing plus scheduling baseline.
- One learned predictor integrated with the planner.
- A browser visualization and reproducible scenario runner.

## Proposed stack and architecture

Python/NumPy for simulation, graph algorithms for planning, PyTorch for prediction, and a lightweight browser UI. A graph neural network is optional after a simpler predictor works.

```text
Layout + orders + faults -> Simulator -> State/features -> Scheduler/planner
                                ^                             |
                                |                         Planned moves
                                +-----------------------------+

Baseline trajectories -> Training data -> Travel-time/congestion predictor
```

Begin with the grid simulator. A 3D simulator, ROS2, or physical robot is a later extension with separate compatibility checks.

## Implementation stages

1. **Simulator correctness:** define time steps, motion, vertex collisions, edge-swap collisions, job completion, and seeded runs.
2. **Classical baseline:** use shortest-path planning with reservations/priorities and a simple assignment policy. Add deadlock handling and measure failures.
3. **Data collection:** generate trajectories over varied layouts, traffic, and fault settings. Separate layouts/seeds for training and evaluation.
4. **Learned prediction:** predict route travel time or local congestion. Start with a simple supervised model before testing a GNN.
5. **Planner integration:** use predictions to alter assignment or routing while retaining collision checks. Measure the whole system, not only prediction error.
6. **Generalization and demo:** evaluate unseen layouts, higher load, urgent tasks, blocked aisles, and failed robots.

## Data and evaluation

Train on simulator-generated data with recorded seeds, policies, and map distributions. Include a baseline evaluated under the same observation access and comparable planning budget as the learned approach.

Measure orders completed per simulation interval, average/tail travel time, total path cost, collisions, deadlocks, urgent-job delay, and planner compute time. Evaluate multiple seeds and report variability.

Compare the classical baseline, a simple congestion heuristic, and learned prediction. Keep simulator configuration, orders, fleet size, and fault sequence fixed in paired comparisons. A better prediction error does not prove better coordination; report operational metrics too.

## Important tests

- Vertex and edge-swap collisions are detected explicitly.
- Impossible jobs terminate or are reported instead of hanging forever.
- A blocked aisle triggers replanning without corrupting reservations.
- A failed robot's occupancy and jobs follow a documented recovery rule.
- A fixed seed reproduces the same scenario.
- Held-out layouts do not enter training through cached/generated trajectories.

## GX10 and optional systems extension

Use CPU simulation initially and the GPU for training the small predictor. Batch simulations only after profiling. Optional: serve the predictor through project 1 and inject network latency/dropouts to compare local versus remote inference with a safe deterministic fallback. This demonstrates simulated systems behavior, not real robot offloading performance.

## Definition of done

Publish a side-by-side demo, fair baseline comparisons, unseen-layout results, and failure cases. Clearly state the limits of simplified physics, sensor assumptions, and simulated traffic.

Deliver simulator code/tests, scenario definitions, baseline planner, prediction training scripts, held-out results, and a visualization. Résumé template: “Built a warehouse fleet simulator; compared learned congestion-aware planning with [baseline], measuring [actual result] across [held-out layouts/seeds].”

## Keep out of the first version

Full humanoid control, foundation-model training, end-to-end reinforcement learning, and expensive physical hardware.
