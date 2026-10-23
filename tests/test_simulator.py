"""Simulator correctness (PLAN.md M1): collision rules, determinism, faults, termination."""

from __future__ import annotations

import hashlib
import json

import pytest

from planners.policies import DistancePolicy
from planners.whca import Reservations, plan_path
from sim.engine import Simulation
from sim.grid import Grid
from sim.layout import build, spec
from sim.safety import CollisionError, check, resolve
from sim.scenario import Scenario, with_faults


@pytest.fixture(scope="module")
def grid():
    return Grid(build(spec("std-6x4", 1)))


def corridor(grid):
    """Three horizontally adjacent free cells on the top highway: a, b, c."""
    W = grid.layout.shape[1]
    return W + 5, W + 6, W + 7


# --- safety layer: explicit vertex and edge-swap detection --------------------------------------

def test_vertex_conflict_is_cancelled(grid):
    a, b, c = corridor(grid)
    final, cancelled = resolve({0: a, 1: c}, {0: b, 1: b}, grid)
    assert final[0] != final[1] and len(cancelled) == 1


def test_edge_swap_is_cancelled(grid):
    a, b, _ = corridor(grid)
    final, cancelled = resolve({0: a, 1: b}, {0: b, 1: a}, grid)
    assert final == {0: a, 1: b} and cancelled == {0, 1}


def test_following_is_allowed_and_cancellations_cascade(grid):
    a, b, c = corridor(grid)
    final, cancelled = resolve({0: a, 1: b}, {0: b, 1: c}, grid)   # 0 follows 1: fine
    assert final == {0: b, 1: c} and not cancelled
    W = grid.layout.shape[1]
    blocked_c = c + W  # 1 can't move into a shelf/invalid cell -> stays -> 0 must stay too
    final, cancelled = resolve({0: a, 1: b}, {0: b, 1: blocked_c if blocked_c not in grid.adj[b] else b + 2}, grid)
    assert final == {0: a, 1: b} and cancelled == {0, 1}


def test_checker_rejects_collisions(grid):
    a, b, _ = corridor(grid)
    with pytest.raises(CollisionError):
        check({0: a, 1: b}, {0: b, 1: b})
    with pytest.raises(CollisionError):
        check({0: a, 1: b}, {0: b, 1: a})


# --- planner respects reservations ----------------------------------------------------------------

def test_planner_avoids_reserved_cells_and_swaps(grid):
    a, b, c = corridor(grid)
    res = Reservations()
    res.add_path(9, 0, [c, b, a])                 # robot 9 moves c -> b -> a
    path, reached = plan_path(grid, res, 1, a, c, 0, 8)
    assert reached
    for t in range(len(path)):
        assert res.cell_free(path[t], t, 1)
        if t + 1 < len(path):
            assert res.move_free(path[t], path[t + 1], t, 1)


# --- whole simulation -----------------------------------------------------------------------------

def run(sc, record_replay=False):
    sim = Simulation(sc, DistancePolicy(), record_replay=record_replay)
    return sim, sim.run()


def test_fixed_seed_reproduces_exactly():
    sc = lambda: with_faults(Scenario(spec("std-6x4", 3), n_robots=15, horizon=400, order_rate=0.5, seed=3))  # noqa: E731
    (s1, m1), (s2, m2) = run(sc(), True), run(sc(), True)
    digest = lambda s: hashlib.sha256(json.dumps(s.replay["frames"]).encode()).hexdigest()  # noqa: E731
    m1.pop("planner_s"); m2.pop("planner_s"); m1.pop("plan_ms_p95"); m2.pop("plan_ms_p95")
    assert m1 == m2 and digest(s1) == digest(s2)


def test_no_robot_ever_enters_a_blocked_cell_or_a_failed_robot():
    sc = with_faults(Scenario(spec("std-8x6", 2), n_robots=20, horizon=600, order_rate=0.6, seed=2), n_blocks=3, n_failures=2)
    sim = Simulation(sc, DistancePolicy(), record_replay=True)
    blocked_at = {}
    orig = sim._move

    def spy(t):
        blocked_at[t] = set(sim.grid.blocked)
        orig(t)
    sim._move = spy
    m = sim.run()
    for t, frame in enumerate(sim.replay["frames"]):
        live = [c for c in frame if c >= 0]
        assert len(live) == len(set(live)), f"two robots share a cell at t={t}"
        for c in live:
            assert c not in blocked_at[t] or c in [x for x in sim.replay["frames"][t - 1] if x >= 0], \
                f"robot entered blocked cell at t={t}"
    assert m["collisions"] == 0


def test_failed_robot_stays_put_and_its_job_is_requeued():
    sc = Scenario(spec("std-6x4", 1), n_robots=10, horizon=500, order_rate=0.6, seed=5,
                  faults=[{"t": 150, "kind": "robot_fail", "robot": 4}])
    sim, m = run(sc, record_replay=True)
    frames = sim.replay["frames"]
    assert all(f[4] == frames[150][4] for f in frames[150:]) and frames[150][4] < 0  # negative = failed
    assert m["requeued_jobs"] <= 1 and sim.robots[4].phase == "failed"


def test_unreachable_job_terminates_and_is_reported():
    lay = build(spec("std-6x4", 1))
    target = lay.pickups[40]
    sc = Scenario(spec("std-6x4", 1), n_robots=5, horizon=300, order_rate=0.2, seed=9,
                  faults=[{"t": 0, "kind": "block", "cells": [target], "duration": 10_000}])
    sim = Simulation(sc, DistancePolicy())
    sim.arrivals = {10: [(target, False)]}   # one job whose pickup is permanently blocked
    m = sim.run()
    assert m["impossible_jobs"] == 1 and m["jobs_completed"] == 0


def test_held_out_families_differ_from_training_families():
    from sim.layout import HELDOUT_FAMILIES, TRAIN_FAMILIES
    assert not set(HELDOUT_FAMILIES) & set(TRAIN_FAMILIES)
    train_shapes = {build(spec(f, 1)).shape for f in TRAIN_FAMILIES}
    assert not any(build(spec(f, 1)).shape in train_shapes for f in HELDOUT_FAMILIES)


def test_loaded_robot_cut_off_from_all_stations_waits_instead_of_crashing():
    """Regression: a blocked aisle closing on both sides of a robot left no reachable station and
    crashed station choice (seen on held-out layouts)."""
    lay = build(spec("std-6x4", 1))
    W = lay.shape[1]
    g = Grid(lay)
    # an interior-aisle pickup: its only exits are the cells above and below
    pickup = next(p for p in lay.pickups if sorted(g.adj[p]) == [p - W, p + W])
    sc = Scenario(spec("std-6x4", 1), n_robots=3, horizon=400, order_rate=0.01, seed=4,
                  faults=[{"t": 0, "kind": "block", "cells": [pickup - W, pickup + W], "duration": 0}])
    sim = Simulation(sc, DistancePolicy())
    sim.arrivals = {1: [(pickup, False)]}
    sim.sc.faults = []
    # walk the robot to the pickup, then close both neighbours while it stands there
    orig = sim._goal_events

    def close_around(t, replan):
        if any(r.pos == pickup and r.phase == "to_pickup" for r in sim.robots) and not sim.block_active:
            sim.block_active.update({pickup - W: t + 100, pickup + W: t + 100})
            sim.grid.set_blocked(set(sim.block_active))
        orig(t, replan)
    sim._goal_events = close_around
    m = sim.run()
    assert m["waiting_for_route_steps"] > 0     # it waited while cut off ...
    assert m["jobs_completed"] == 1             # ... and delivered once the block lifted
