"""Task assignment and station choice. All policies share the WHCA* router; they differ only in
how they estimate the cost of sending a robot somewhere:

  distance    shortest-path distance on the static map (classical baseline)
  heuristic   distance inflated by robots on the path and by robots already heading to the goal
              (a hand-written congestion model)
  learned     a trained travel-time predictor over the same decision-time features

Assignment: optimal robot-to-job matching (Hungarian) on estimated time to pickup, with urgent jobs
favoured by a fixed bonus. Station: the one with the lowest estimated travel time.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from predictor.features import trip_features
from sim.grid import UNREACHABLE

URGENT_BONUS = 40.0   # steps of estimated travel an urgent job is allowed to "jump"
INFEASIBLE = 1e9


class Policy:
    name = "base"

    def cost(self, sim, robot, goal: int) -> float:
        raise NotImplementedError

    def costs(self, sim, pairs: list[tuple]) -> list[float]:
        """Estimated travel time for many (robot, goal) pairs; overridden for batched models."""
        return [self.cost(sim, r, g) for r, g in pairs]

    def features(self, sim, robot, goal: int) -> dict:
        return trip_features(sim, robot, goal)

    def assign(self, sim, t: int, robots: list, jobs: list) -> list[tuple]:
        if not robots or not jobs:
            return []
        # Bound the matrix: only the oldest/urgent jobs are candidates, which keeps per-step cost flat.
        jobs = sorted(jobs, key=lambda j: (not j.urgent, j.created))[: max(len(robots) * 3, 10)]
        C = np.full((len(robots), len(jobs)), INFEASIBLE)
        cells = [(i, k) for i, r in enumerate(robots) for k, j in enumerate(jobs)
                 if sim.dist(r.pos, j.pickup) < UNREACHABLE]
        estimates = self.costs(sim, [(robots[i], jobs[k].pickup) for i, k in cells])
        for (i, k), est in zip(cells, estimates):
            C[i, k] = est - (URGENT_BONUS if jobs[k].urgent else 0.0)
        rows, cols = linear_sum_assignment(C)
        return [(robots[i], jobs[k]) for i, k in zip(rows, cols) if C[i, k] < INFEASIBLE / 2]

    def choose_station(self, sim, robot) -> int | None:
        """Best reachable station, or None if the robot is currently cut off from all of them."""
        stations = [s for s in sim.layout.stations if sim.dist(robot.pos, s) < UNREACHABLE]
        if not stations:
            return None
        estimates = self.costs(sim, [(robot, s) for s in stations])
        return min(zip(estimates, stations))[1]


class DistancePolicy(Policy):
    name = "distance"

    def cost(self, sim, robot, goal: int) -> float:
        return float(sim.dist(robot.pos, goal))


class HeuristicPolicy(Policy):
    """Hand-tuned congestion model: each robot on the static path costs `per_robot` steps, each
    robot already heading to the same goal costs `per_queued` steps (stations queue)."""
    name = "heuristic"

    def __init__(self, per_robot: float = 2.0, per_queued: float = 6.0):
        self.per_robot, self.per_queued = per_robot, per_queued

    def cost(self, sim, robot, goal: int) -> float:
        f = trip_features(sim, robot, goal)
        return f["dist"] + self.per_robot * f["robots_on_path"] + self.per_queued * f["heading_to_goal"]


class LearnedPolicy(Policy):
    name = "learned"

    def __init__(self, model):
        self.model = model  # predictor.model.TravelTimeModel

    def cost(self, sim, robot, goal: int) -> float:
        return self.costs(sim, [(robot, goal)])[0]

    def costs(self, sim, pairs: list[tuple]) -> list[float]:
        if not pairs:
            return []
        return list(self.model.predict([trip_features(sim, r, g) for r, g in pairs]))


POLICIES = {"distance": DistancePolicy, "heuristic": HeuristicPolicy}
