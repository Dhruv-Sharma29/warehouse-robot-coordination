"""Trip features available at decision time (when a robot is about to be sent somewhere).

Used by the congestion heuristic and the learned predictor, and logged with the realised travel
time to build training data. Only information a real fleet manager has at that moment: robot
positions, robots' current goals, the static map and blocked cells. No future knowledge.
"""

from __future__ import annotations

FEATURES = ["dist", "robots_on_path", "robots_on_path_per_cell", "robots_near_start", "robots_near_goal",
            "heading_near_goal", "heading_to_goal", "goal_is_station", "narrow_frac", "turns", "fleet_density"]


def manhattan(layout, a: int, b: int) -> int:
    (ra, ca), (rb, cb) = layout.rc(a), layout.rc(b)
    return abs(ra - rb) + abs(ca - cb)


def trip_features(sim, robot, goal: int) -> dict:
    layout, grid = sim.layout, sim.grid
    others = [r for r in sim.active_robots() if r.id != robot.id]
    path = grid.shortest_path(robot.pos, goal)
    on_path = set(path[1:])
    dist = max(0, len(path) - 1) if path else 10_000
    turns = 0
    for i in range(2, len(path)):
        if (path[i] - path[i - 1]) != (path[i - 1] - path[i - 2]):
            turns += 1
    narrow = sum(1 for c in path if len(grid.adj[c]) <= 2) / max(1, len(path))
    robots_on_path = sum(1 for r in others if r.pos in on_path)
    return {
        "dist": dist,
        "robots_on_path": robots_on_path,
        "robots_on_path_per_cell": robots_on_path / max(1, dist),
        "robots_near_start": sum(1 for r in others if manhattan(layout, r.pos, robot.pos) <= 3),
        "robots_near_goal": sum(1 for r in others if manhattan(layout, r.pos, goal) <= 3),
        "heading_near_goal": sum(1 for r in others if r.goal is not None and manhattan(layout, r.goal, goal) <= 2),
        "heading_to_goal": sum(1 for r in others if r.goal == goal),
        "goal_is_station": int(goal in layout.stations),
        "narrow_frac": narrow,
        "turns": turns,
        "fleet_density": len(others) / max(1, sum(grid.free)),
    }
