"""Procedural warehouse layouts.

A layout is a grid of free cells and shelves:

    row 0          parking (top highway, also parking along both side columns)
    row 1          top highway
    block rows     [aisle | shelf shelf | aisle | shelf shelf | ... | aisle]  for `block_len` rows,
                   then a 1-wide cross aisle
    2 rows         bottom highway; drop-off stations are cells of its lower lane (pass-through)
    last row       wall

Pickups are aisle cells next to a shelf. A seeded fraction of shelf segments is removed so
layouts in the same family still differ. Train and held-out layouts come from different families
(different geometry, not just different seeds), so held-out results test generalisation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

FREE, SHELF, WALL = 0, 1, 2


@dataclass(frozen=True)
class LayoutSpec:
    family: str
    n_aisles: int        # shelf double-columns; there are n_aisles + 1 picking aisles
    block_len: int       # shelf block height
    n_block_rows: int
    n_stations: int
    removed_frac: float  # fraction of shelf segments removed (shortcuts, irregularity)
    seed: int

    @property
    def name(self) -> str:
        return f"{self.family}-s{self.seed}"


@dataclass
class Layout:
    spec: LayoutSpec
    grid: np.ndarray            # H x W of FREE / SHELF / WALL
    pickups: list[int]          # cell ids
    stations: list[int]
    parking: list[int]

    @property
    def shape(self) -> tuple[int, int]:
        return self.grid.shape

    def cell(self, r: int, c: int) -> int:
        return r * self.grid.shape[1] + c

    def rc(self, cell: int) -> tuple[int, int]:
        return divmod(cell, self.grid.shape[1])


def build(spec: LayoutSpec) -> Layout:
    rng = random.Random(spec.seed)
    W = 1 + spec.n_aisles * 3 + 1 + 1
    H = 2 + spec.n_block_rows * (spec.block_len + 1) + 1 + 1
    g = np.full((H, W), FREE, dtype=np.int8)
    shelf_cols = [1 + i * 3 + j for i in range(spec.n_aisles) for j in (1, 2)]
    for b in range(spec.n_block_rows):
        top = 2 + b * (spec.block_len + 1)
        for col in shelf_cols:
            for r in range(top, top + spec.block_len):
                g[r, col] = SHELF
        # remove a few 2-cell shelf segments to create irregular shortcuts
        for col in shelf_cols[::2]:
            if rng.random() < spec.removed_frac:
                r0 = top + rng.randrange(0, max(1, spec.block_len - 1))
                g[r0:r0 + 2, col:col + 2] = FREE
    g[H - 1, :] = WALL
    # Stations sit on the highway's lower lane, not in dead-end pockets in the wall: a first version
    # put them in pockets, and a robot waiting on the pocket's only exit deadlocked the robot inside.
    station_cols = np.linspace(2, W - 3, spec.n_stations).round().astype(int)
    lay = Layout(spec, g, [], [], [])
    lay.stations = [lay.cell(H - 2, int(c)) for c in station_cols]
    for r in range(2, H - 3):
        for c in range(W):
            if g[r, c] == FREE and any(0 <= r + dr < H and 0 <= c + dc < W and g[r + dr, c + dc] == SHELF
                                       for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                lay.pickups.append(lay.cell(r, c))
    lay.parking = [lay.cell(0, c) for c in range(W)] + \
                  [lay.cell(r, c) for r in range(2, H - 3) for c in (0, W - 1)]
    return lay


TRAIN_FAMILIES = {
    "std-6x4": dict(n_aisles=6, block_len=4, n_block_rows=4, n_stations=4, removed_frac=0.08),
    "std-8x6": dict(n_aisles=8, block_len=6, n_block_rows=3, n_stations=4, removed_frac=0.08),
}
HELDOUT_FAMILIES = {
    "wide-10x5": dict(n_aisles=10, block_len=5, n_block_rows=3, n_stations=5, removed_frac=0.12),
    "long-7x8-2st": dict(n_aisles=7, block_len=8, n_block_rows=2, n_stations=2, removed_frac=0.05),
}


# Fleet-size scaling only (never used for training or the policy comparison): room for 100+ robots.
SCALING_FAMILIES = {
    "xl-14x6": dict(n_aisles=14, block_len=6, n_block_rows=5, n_stations=6, removed_frac=0.08),
}


def spec(family: str, seed: int) -> LayoutSpec:
    params = {**TRAIN_FAMILIES, **HELDOUT_FAMILIES, **SCALING_FAMILIES}[family]
    return LayoutSpec(family=family, seed=seed, **params)


def render(layout: Layout, robots: dict[int, int] | None = None) -> str:
    """ASCII picture for debugging and tests: # shelf, X wall, S station, digits robots."""
    H, W = layout.shape
    chars = [["." if layout.grid[r, c] == FREE else "#" if layout.grid[r, c] == SHELF else "X"
              for c in range(W)] for r in range(H)]
    for s in layout.stations:
        r, c = layout.rc(s)
        chars[r][c] = "S"
    for rid, cell in (robots or {}).items():
        r, c = layout.rc(cell)
        chars[r][c] = str(rid % 10)
    return "\n".join("".join(row) for row in chars)
