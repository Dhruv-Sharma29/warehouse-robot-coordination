"""Discrete-time warehouse simulation.

Per step: faults -> order arrivals -> goal events (pickup / drop-off) -> assignment -> planning ->
safety layer -> movement -> metrics. Everything is seeded, so a scenario replays identically.

Recovery rules (documented, tested):
- A failed robot stays where it stopped and becomes an obstacle. Its job goes back to the queue
  (the item is picked again from the shelf), counted in `requeued_jobs`.
- A blocked aisle segment closes each cell as soon as it is unoccupied and reopens after its
  duration. Every robot replans immediately.
- A job whose pickup is unreachable is skipped by assignment until reachable again. Jobs still
  pending and unreachable at the end are reported as `impossible_jobs`: the run never hangs.
- A loaded robot cut off from every station (a blocked aisle can close on both sides of it) keeps
  its job, holds position, and retries station choice every step (`waiting_for_route_steps`).
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from planners.whca import WhcaRouter
from sim.grid import UNREACHABLE, Grid
from sim.layout import Layout, build
from sim.scenario import Scenario
from sim.safety import resolve

STUCK_STEPS = 30  # no progress toward the goal for this long = one stuck (deadlock/livelock) episode


@dataclass
class Job:
    id: int
    created: int
    pickup: int
    urgent: bool
    deadline: int | None
    robot: int | None = None
    picked: int | None = None
    done: int | None = None
    station: int | None = None
    requeued: int = 0


@dataclass
class Robot:
    id: int
    pos: int
    phase: str = "idle"            # idle | parking | to_pickup | need_station | to_station | failed
    goal: int | None = None
    job: int | None = None
    path: list[int] = field(default_factory=list)
    trip: dict | None = None       # {"start_t", "features", "kind"} for the current leg
    best_dist: int = 0
    since_progress: int = 0
    stuck_reported: bool = False


class Simulation:
    def __init__(self, scenario: Scenario, policy, window: int = 16, replan_every: int = 4,
                 record_trips: bool = False, record_replay: bool = False, router_mode: str = "rolling"):
        self.sc = scenario
        self.layout: Layout = build(scenario.layout)
        self.grid = Grid(self.layout)
        self.policy = policy
        self.router = WhcaRouter(self.grid, window, replan_every, mode=router_mode)
        self.rng = random.Random(scenario.seed)
        parking = sorted(self.layout.parking)
        assert scenario.n_robots <= len(parking), "more robots than parking cells"
        step = len(parking) / scenario.n_robots
        self.robots = [Robot(i, parking[int(i * step)]) for i in range(scenario.n_robots)]
        self.jobs: list[Job] = []
        self.arrivals = scenario.arrivals(self.layout)
        self.block_active: dict[int, int] = {}     # cell -> until t
        self.block_pending: dict[int, int] = {}
        self.record_trips, self.trips = record_trips, []
        self.record_replay = record_replay
        self.replay = {"layout": self.layout.grid.tolist(), "stations": self.layout.stations, "frames": [], "events": []}
        self.m = {"moves": 0, "waits": 0, "safety_interventions": 0, "stuck_episodes": 0, "requeued_jobs": 0,
                  "waiting_for_route_steps": 0,
                  "planner_s": 0.0, "plan_ms_per_step": []}
        self.full_replan = True

    # --- helpers used by policies --------------------------------------------------------------
    def active_robots(self) -> list[Robot]:
        return [r for r in self.robots if r.phase != "failed"]

    def dist(self, a: int, b: int) -> int:
        return int(self.grid.dist_to(b)[a])

    # --- step phases -----------------------------------------------------------------------------
    def _faults(self, t: int) -> None:
        for f in self.sc.faults:
            if f["t"] == t and f["kind"] == "block":
                for c in f["cells"]:
                    self.block_pending[c] = t + f["duration"]
                self.replay["events"].append({"t": t, "kind": "block", "cells": f["cells"], "duration": f["duration"]})
            if f["t"] == t and f["kind"] == "robot_fail":
                r = self.robots[f["robot"] % len(self.robots)]
                if r.phase != "failed":
                    self._fail(t, r)
        occupied = {r.pos for r in self.robots}
        for c, until in list(self.block_pending.items()):
            if c not in occupied:
                self.block_active[c] = until
                del self.block_pending[c]
        for c, until in list(self.block_active.items()):
            if t >= until:
                del self.block_active[c]
        failed = {r.pos for r in self.robots if r.phase == "failed"}
        blocked = set(self.block_active) | failed
        if blocked != self.grid.blocked:
            self.grid.set_blocked(blocked)
            self.full_replan = True

    def _fail(self, t: int, r: Robot) -> None:
        if r.job is not None:
            job = self.jobs[r.job]
            job.robot, job.picked, job.station = None, None, None
            job.requeued += 1
            self.m["requeued_jobs"] += 1
        r.phase, r.goal, r.job, r.path, r.trip = "failed", None, None, [], None
        self.router.res.release(r.id)
        self.replay["events"].append({"t": t, "kind": "robot_fail", "robot": r.id})

    def _arrivals(self, t: int) -> None:
        for pickup, urgent in self.arrivals.get(t, []):
            self.jobs.append(Job(len(self.jobs), t, pickup, urgent, t + self.sc.urgent_deadline if urgent else None))

    def _start_trip(self, t: int, r: Robot, goal: int, kind: str) -> None:
        r.goal = goal
        r.best_dist, r.since_progress, r.stuck_reported = self.dist(r.pos, goal), 0, False
        features = self.policy.features(self, r, goal) if self.record_trips else None
        r.trip = {"start_t": t, "kind": kind, "features": features}

    def _end_trip(self, t: int, r: Robot) -> None:
        if self.record_trips and r.trip and r.trip["kind"] != "parking":
            self.trips.append({**r.trip["features"], "kind": r.trip["kind"], "actual": t - r.trip["start_t"]})
        r.trip = None

    def _goal_events(self, t: int, replan: set) -> None:
        for r in self.active_robots():
            if r.goal is None or r.pos != r.goal:
                continue
            if r.phase == "to_pickup":
                self._end_trip(t, r)
                self.jobs[r.job].picked = t
                r.phase = "need_station"
            if r.phase == "need_station":
                station = self.policy.choose_station(self, r)
                if station is None:       # cut off from every station: hold and retry next step
                    self.m["waiting_for_route_steps"] += 1
                    continue
                self.jobs[r.job].station = station
                r.phase = "to_station"
                self._start_trip(t, r, station, "to_station")
                replan.add(r.id)
            elif r.phase == "to_station":
                self._end_trip(t, r)
                self.jobs[r.job].done = t
                r.phase, r.job, r.goal = "idle", None, None
            elif r.phase == "parking":
                r.trip = None

    def _assign(self, t: int, replan: set) -> None:
        free = [r for r in self.active_robots() if r.phase in ("idle", "parking")]
        if not free:
            return
        pending = [j for j in self.jobs if j.robot is None and j.done is None]
        reachable = [j for j in pending if any(self.dist(r.pos, j.pickup) < UNREACHABLE for r in free)]
        for r, j in self.policy.assign(self, t, free, reachable):
            j.robot, r.job, r.phase = r.id, j.id, "to_pickup"
            self._start_trip(t, r, j.pickup, "to_pickup")
            replan.add(r.id)
        taken = {x.goal for x in self.robots if x.phase == "parking"}
        for r in free:
            if r.phase == "idle":
                options = [p for p in self.layout.parking if p not in taken and self.grid.passable(p)]
                d = self.grid.dist_to
                goal = min(options, key=lambda p: (d(p)[r.pos], p)) if options else r.pos
                taken.add(goal)
                r.phase = "parking"
                self._start_trip(t, r, goal, "parking")
                replan.add(r.id)

    def _priority(self, t: int) -> list[Robot]:
        def key(r: Robot):
            urgent = r.job is not None and self.jobs[r.job].urgent
            working = r.phase in ("to_pickup", "to_station")
            return (-r.since_progress if r.since_progress >= STUCK_STEPS else 0, not urgent, not working,
                    (r.id + t // self.router.replan_every) % len(self.robots))
        return sorted(self.active_robots(), key=key)

    def _plan(self, t: int, replan: set) -> None:
        t0 = time.perf_counter()
        if self.full_replan or t % self.router.replan_every == 0:
            self.router.replan_all(t, self._priority(t))
            self.full_replan = False
        else:
            for r in self._priority(t):
                if r.id in replan or not r.path:
                    self.router.replan_one(t, r)
        dt = time.perf_counter() - t0
        self.m["planner_s"] += dt
        self.m["plan_ms_per_step"].append(dt * 1000)

    def _move(self, t: int) -> None:
        active = self.active_robots()
        cur = {r.id: r.pos for r in active}
        proposed = {r.id: (r.path[0] if r.path else r.pos) for r in active}
        final, cancelled = resolve(cur, proposed, self.grid)
        if cancelled:
            self.m["safety_interventions"] += len(cancelled)
            self.full_replan = True
        for r in active:
            nxt = final[r.id]
            if r.path and r.path[0] == nxt:
                r.path.pop(0)
            elif r.id in cancelled:
                r.path = []
            self.m["moves" if nxt != r.pos else "waits"] += 1
            r.pos = nxt
            if r.goal is not None and r.phase in ("to_pickup", "to_station", "parking"):
                d = self.dist(r.pos, r.goal)
                if d < r.best_dist:
                    r.best_dist, r.since_progress, r.stuck_reported = d, 0, False
                elif d > 0:
                    r.since_progress += 1
                    if r.since_progress >= STUCK_STEPS and not r.stuck_reported:
                        self.m["stuck_episodes"] += 1
                        r.stuck_reported = True

    def run(self) -> dict:
        for t in range(self.sc.horizon):
            replan: set[int] = set()
            self._faults(t)
            self._arrivals(t)
            self._goal_events(t, replan)
            self._assign(t, replan)
            self._plan(t, replan)
            self._move(t)
            if self.record_replay:
                self.replay["frames"].append([r.pos if r.phase != "failed" else -1 - r.pos for r in self.robots])
        return self.metrics()

    def metrics(self) -> dict:
        done = [j for j in self.jobs if j.done is not None]
        cycle = sorted(j.done - j.created for j in done)
        urgent = [j for j in self.jobs if j.urgent and j.deadline is not None and j.deadline < self.sc.horizon]
        urgent_done = [j for j in urgent if j.done is not None]
        pending = [j for j in self.jobs if j.done is None]
        free = [r for r in self.robots if r.phase != "failed"]
        impossible = [j for j in pending if j.robot is None and all(self.dist(r.pos, j.pickup) >= UNREACHABLE for r in free)]
        steps = self.m["plan_ms_per_step"]
        return {
            "jobs_created": len(self.jobs), "jobs_completed": len(done),
            "throughput_per_100_steps": round(100 * len(done) / self.sc.horizon, 2),
            "cycle_mean": round(sum(cycle) / len(cycle), 1) if cycle else None,
            "cycle_p95": cycle[max(0, math.ceil(0.95 * len(cycle)) - 1)] if cycle else None,
            "urgent_due": len(urgent), "urgent_missed": sum(1 for j in urgent if j.done is None or j.done > j.deadline),
            "urgent_cycle_mean": round(sum(j.done - j.created for j in urgent_done) / len(urgent_done), 1) if urgent_done else None,
            "moves": self.m["moves"], "waits": self.m["waits"],
            "collisions": 0,  # impossible by construction: sim.safety.resolve asserts it every step
            "safety_interventions": self.m["safety_interventions"],
            "stuck_episodes": self.m["stuck_episodes"],
            "robots_stuck_at_end": sum(1 for r in free if r.since_progress >= STUCK_STEPS),
            "requeued_jobs": self.m["requeued_jobs"], "impossible_jobs": len(impossible),
            "waiting_for_route_steps": self.m["waiting_for_route_steps"],
            "pending_at_end": len(pending),
            "planner_s": round(self.m["planner_s"], 2),
            "plan_ms_p95": round(sorted(steps)[int(0.95 * (len(steps) - 1))], 2) if steps else None,
            "astar_calls": self.router.calls,
        }
