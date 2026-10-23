"""Windowed cooperative A* (WHCA*): the classical collision-avoidance baseline.

Each robot plans a path through (cell, time) for the next `window` steps, avoiding cells and moves
reserved by other robots. Every `replan_every` steps all robots replan in priority order; robots
that get a new goal between rounds replan alone around the current reservations.

Two round modes (an ablation in results/):
  rolling (default)  robots replan one at a time, each releasing only its own reservations and
                     planning around everyone else's current plans. Every robot's old plan is still
                     valid for at least window - replan_every steps, so a valid plan for the next
                     replan_every executed steps always exists: execution is conflict-free by construction.
  clear              all reservations are dropped and robots replan from scratch in priority order;
                     unplanned robots are treated as obstacles for `avoid_steps` steps. Conflicts
                     it can't prevent fall to the simulator's safety layer.

Rules mirror the simulator: no two robots in one cell at the same time (vertex conflict), no two
robots swapping cells in one step (edge conflict). Following a robot into the cell it is leaving
is allowed.

"""

from __future__ import annotations

import heapq
from collections import defaultdict

from sim.grid import UNREACHABLE, Grid


class Reservations:
    def __init__(self) -> None:
        self.vertex: dict[tuple[int, int], int] = {}
        self.edge: dict[tuple[int, int, int], int] = {}   # (from, to, t): moving from at t to `to` at t+1
        self.owned: dict[int, list[tuple]] = defaultdict(list)

    def add_path(self, rid: int, t0: int, cells: list[int]) -> None:
        for i, c in enumerate(cells):
            key = (c, t0 + i)
            self.vertex[key] = rid
            self.owned[rid].append(("v", key))
        for i in range(len(cells) - 1):
            if cells[i] != cells[i + 1]:
                key = (cells[i], cells[i + 1], t0 + i)
                self.edge[key] = rid
                self.owned[rid].append(("e", key))

    def release(self, rid: int) -> None:
        for kind, key in self.owned.pop(rid, []):
            table = self.vertex if kind == "v" else self.edge
            if table.get(key) == rid:
                del table[key]

    def clear(self) -> None:
        self.vertex.clear()
        self.edge.clear()
        self.owned.clear()

    def cell_free(self, c: int, t: int, rid: int) -> bool:
        return self.vertex.get((c, t), rid) == rid

    def move_free(self, a: int, b: int, t: int, rid: int) -> bool:
        return a == b or self.edge.get((b, a, t), rid) == rid


def plan_path(grid: Grid, res: Reservations, rid: int, start: int, goal: int, t0: int, window: int,
              avoid: dict[int, int] | None = None) -> tuple[list[int], bool]:
    """Cells for t0..t0+window (start first). Returns (path, reached_goal_within_window).

    `avoid` maps cell -> last time step it must not be entered (cells of robots not yet planned).
    If the goal can't be reached and held until the window ends, returns the best partial path:
    the reachable state at the window's end closest to the goal. If no state at the window's end is
    reachable (boxed in), returns the deepest valid path found, then holds position.
    """
    avoid = avoid or {}
    dist = grid.dist_to(goal)
    if dist[start] >= UNREACHABLE:
        goal, dist = start, grid.dist_to(start)  # nowhere to go: hold position as well as possible
    adj, blocked = grid.adj, grid.blocked
    end_t = t0 + window
    start_h = int(dist[start])
    heap = [(start_h, 0, start_h, start, 0)]  # (f, -g, h, cell, g)
    parent: dict[tuple[int, int], tuple[int, int] | None] = {(start, 0): None}
    deepest = (0, -start_h, start)
    while heap:
        _, _, h, cell, g = heapq.heappop(heap)
        deepest = max(deepest, (g, -h, cell))
        t = t0 + g
        if cell == goal and all(res.cell_free(goal, tt, rid) for tt in range(t + 1, end_t + 1)):
            return _unwind(parent, (cell, g), window), True
        if g == window:
            return _unwind(parent, (cell, g), window), False   # best partial (A* pops min f = window + h)
        for nxt in (cell, *adj[cell]):
            if nxt in blocked or (nxt, g + 1) in parent:
                continue
            if not res.cell_free(nxt, t + 1, rid) or not res.move_free(cell, nxt, t, rid):
                continue
            if nxt != cell and avoid.get(nxt, -1) >= t + 1:
                continue
            parent[(nxt, g + 1)] = (cell, g)
            nh = int(dist[nxt])
            heapq.heappush(heap, (g + 1 + nh, -(g + 1), nh, nxt, g + 1))
    g, _, cell = deepest  # boxed in: deepest valid prefix, then hold (safety layer protects the rest)
    return _unwind(parent, (cell, g), window), False


def _unwind(parent: dict, node: tuple[int, int], window: int) -> list[int]:
    cells = []
    while node is not None:
        cells.append(node[0])
        node = parent[node]
    cells.reverse()
    return cells + [cells[-1]] * (window + 1 - len(cells))


class WhcaRouter:
    def __init__(self, grid: Grid, window: int = 16, replan_every: int = 4, mode: str = "rolling",
                 avoid_steps: int = 2):
        assert 2 * replan_every <= window, "rolling mode needs an old plan valid through the next round"
        self.grid, self.window, self.replan_every = grid, window, replan_every
        self.mode, self.avoid_steps = mode, avoid_steps
        self.res = Reservations()
        self.calls = 0

    def replan_all(self, t: int, robots: list) -> None:
        """Replan every active robot in the given priority order."""
        if self.mode == "clear":
            self.res.clear()
            unplanned = {r.id: r.pos for r in robots}
            for r in robots:
                del unplanned[r.id]
                avoid = {pos: t + self.avoid_steps for pos in unplanned.values()}
                self._plan(t, r, avoid)
            return
        # Robots whose reservations no longer match where they stand (e.g. a move was cancelled)
        # first get a placeholder reserving their actual cell, so nobody plans into it.
        for r in robots:
            if self.res.vertex.get((r.pos, t)) != r.id:
                self.res.release(r.id)
                self.res.add_path(r.id, t, [r.pos, r.pos])
        for r in robots:
            self.replan_one(t, r)

    def replan_one(self, t: int, r) -> None:
        self.res.release(r.id)
        self._plan(t, r, None)

    def _plan(self, t: int, r, avoid) -> None:
        goal = r.goal if r.goal is not None else r.pos
        path, _ = plan_path(self.grid, self.res, r.id, r.pos, goal, t, self.window, avoid)
        self.calls += 1
        self.res.add_path(r.id, t, path)
        r.path = path[1:]
