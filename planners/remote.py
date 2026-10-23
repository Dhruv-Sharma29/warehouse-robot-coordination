"""Learned travel-time estimates from a remote predictor (predictor/serve.py), with a deterministic
fallback when the service is slow or down.

Each batch of (robot, goal) estimates is one HTTP call with a time budget. A timeout, a dropped
connection or a bad reply falls back to the tuned heuristic for that batch, so assignment and
station choice always get an answer. After `trip` consecutive failures a circuit breaker skips the
service for the next `cooldown` batches, then tries it again. Both counters are in calls, not wall
time, so for a given sequence of service replies the policy's choices are deterministic.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from planners.policies import HeuristicPolicy, Policy
from predictor.features import trip_features


class RemotePolicy(Policy):
    name = "remote"

    def __init__(self, url: str, budget_s: float = 0.1, trip: int = 3, cooldown: int = 50, fallback: Policy | None = None):
        self.url, self.budget_s, self.trip, self.cooldown = url, budget_s, trip, cooldown
        self.fallback = fallback or HeuristicPolicy()
        self.failures_in_a_row = self.skip = 0
        self.stats = {"remote": 0, "fallback": 0, "failed_calls": 0, "circuit_opened": 0}

    def cost(self, sim, robot, goal: int) -> float:
        return self.costs(sim, [(robot, goal)])[0]

    def costs(self, sim, pairs: list[tuple]) -> list[float]:
        if not pairs:
            return []
        if self.skip:
            self.skip -= 1
            return self._fallback(sim, pairs)
        rows = [trip_features(sim, r, g) for r, g in pairs]
        try:
            req = urllib.request.Request(self.url, data=json.dumps({"rows": rows}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.budget_s) as resp:
                pred = json.loads(resp.read())["pred"]
            if len(pred) != len(pairs):
                raise ValueError("wrong number of estimates")
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            self.stats["failed_calls"] += 1
            self.failures_in_a_row += 1
            if self.failures_in_a_row >= self.trip:
                self.skip, self.failures_in_a_row = self.cooldown, 0
                self.stats["circuit_opened"] += 1
            return self._fallback(sim, pairs)
        self.failures_in_a_row = 0
        self.stats["remote"] += 1
        return [float(p) for p in pred]

    def _fallback(self, sim, pairs: list[tuple]) -> list[float]:
        self.stats["fallback"] += 1
        return self.fallback.costs(sim, pairs)
