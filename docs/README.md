# Warehouse robot coordination — Documentation

A deterministic grid-warehouse simulator with a collision-free multi-robot router, and a paired
study of whether a learned travel-time predictor improves fleet operations over a tuned classical
baseline on unseen layouts.

These docs are the plan and the design record. They are written to be read in order the first
time and used as reference afterwards. To run things, start with [start.md](../start.md).

## Reading order

| # | Doc | What it settles |
| --- | --- | --- |
| 00 | [Charter](00-charter.md) | The question, scope and non-goals, success criteria mapped to tests and results |
| 01 | [Architecture](01-architecture.md) | The step loop, the three design rules, components, robot states, repo layout |
| 02 | [Coordination](02-coordination.md) | Conflict model, rolling WHCA*, the safety layer, fault recovery, scaling |
| 03 | [Cost estimators](03-estimators.md) | Distance vs heuristic vs learned, features, splits, models, accuracy, on-policy round |
| 04 | [Evaluation](04-evaluation.md) | Paired design, baselines, statistics, every closed-loop result, what it doesn't show |
| 05 | [Risks](05-risks.md) | Thesis and delivery risks, claim hygiene, the question to have an answer for |
| 06 | [Roadmap](06-roadmap.md) | Milestone status with evidence, definition of done, next experiments |
| 07 | [Learning checklist](07-learning-checklist.md) | Skills per milestone; interview points mapped to what was built |
| 08 | [Implementation notes](08-implementation-notes.md) | Where the code departs from PLAN.md, and why |

Brief: [SPEC.md](../SPEC.md) · Plan and progress: [PLAN.md](../PLAN.md)

## The one-paragraph version

Learned-planning demos usually compare a model against a naive baseline and win. This project
is built around the opposite comparison: **the learned predictor has to beat a tuned congestion
heuristic that sees the same inputs**, with the router, safety layer, orders, faults and seeds
held identical, on layout families it never saw. What makes it non-trivial is the classical
side: a rolling windowed cooperative A* router that took throughput up 23.5% and safety
interventions from ~434 to 0 per run on the ablation, and a safety layer that makes collisions
impossible regardless of the planner. The answer is a clean negative: the MLP is 21–22% more
accurate than shortest-path distance on held-out layouts, but its closed-loop advantage over the
heuristic is not significant on any metric, and a round of retraining on its own trips made
saturated throughput significantly worse.

## Status

**All six PLAN.md milestones done** (PLAN.md Progress, 2026-10-06), plus one follow-up round of
on-policy data aggregation. The optional systems extension was added on 2026-10-23: the predictor
served over HTTP with injected latency and drops, and a deterministic fallback that is never
unsafe (0 collisions) and degrades exactly to the heuristic when the service is down. The
macOS path has not been run on a real Mac. See [06-roadmap.md](06-roadmap.md) for what would come
next and [08-implementation-notes.md](08-implementation-notes.md) for the places where building it
changed the plan, including a router replacement that forced every result to be redone.

## Conventions used in these docs

- **MUST / SHOULD / MAY** are load-bearing. MUST items are acceptance criteria.
- Anything marked **[verify]** is a claim not confirmed against a primary source or on the
  machine in question; confirm before relying on it.
- Every number cites the file it comes from, usually under `results/summary/`. Where a figure is
  derived (for example a paired difference not stored in a summary), the doc says how.
- "Significant" means a paired 95% t-interval that excludes zero; no multiple-comparison
  correction is applied ([04](04-evaluation.md) § Statistics).
