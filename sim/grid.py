"""Grid connectivity and shortest-path distances, with dynamically blocked cells (blocked aisles,
failed robots). Distances are breadth-first, cached per target, and invalidated by a version
counter whenever the blocked set changes."""

from __future__ import annotations

from collections import deque

import numpy as np

from sim.layout import FREE, Layout

UNREACHABLE = 1 << 20


class Grid:
    def __init__(self, layout: Layout):
        self.layout = layout
        H, W = layout.shape
        self.n = H * W
        self.free = [bool(layout.grid[c // W, c % W] == FREE) for c in range(self.n)]
        self.adj: list[list[int]] = [[] for _ in range(self.n)]
        for c in range(self.n):
            if not self.free[c]:
                continue
            r, col = divmod(c, W)
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, col + dc
                if 0 <= rr < H and 0 <= cc < W and self.free[rr * W + cc]:
                    self.adj[c].append(rr * W + cc)
        self.blocked: set[int] = set()
        self.version = 0
        self._cache: dict[int, tuple[int, np.ndarray]] = {}

    def passable(self, c: int) -> bool:
        return self.free[c] and c not in self.blocked

    def set_blocked(self, cells: set[int]) -> None:
        if cells != self.blocked:
            self.blocked = set(cells)
            self.version += 1

    def dist_to(self, target: int) -> np.ndarray:
        """Distance from every cell to `target` (UNREACHABLE where no path), honouring blocks."""
        hit = self._cache.get(target)
        if hit and hit[0] == self.version:
            return hit[1]
        d = np.full(self.n, UNREACHABLE, dtype=np.int32)
        if self.passable(target):
            d[target] = 0
            q = deque([target])
            while q:
                c = q.popleft()
                nd = d[c] + 1
                for nb in self.adj[c]:
                    if d[nb] == UNREACHABLE and nb not in self.blocked:
                        d[nb] = nd
                        q.append(nb)
        self._cache[target] = (self.version, d)
        return d

    def shortest_path(self, start: int, goal: int) -> list[int]:
        """One static shortest path (ties broken by neighbour order), for features."""
        d = self.dist_to(goal)
        if d[start] >= UNREACHABLE:
            return []
        path, c = [start], start
        while c != goal:
            c = min((nb for nb in self.adj[c] if nb not in self.blocked), key=lambda nb: d[nb])
            path.append(c)
        return path
