"""Scenarios: layout + fleet size + order stream + fault schedule, all derived from one seed.

Orders arrive as a Poisson process. Half the picks concentrate around two seeded hotspots (the
uneven demand that creates congestion), the rest are uniform over pickup cells. 10% are urgent,
with a deadline. Faults: blocked aisle segments and robot failures at seeded times.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

from sim.layout import FREE, SHELF, Layout, LayoutSpec, build


@dataclass
class Scenario:
    layout: LayoutSpec
    n_robots: int
    horizon: int
    order_rate: float            # mean orders per step
    seed: int
    urgent_frac: float = 0.10
    urgent_deadline: int = 200
    hotspot_frac: float = 0.5
    faults: list[dict] = field(default_factory=list)

    def arrivals(self, layout: Layout) -> dict[int, list[tuple[int, bool]]]:
        rng = random.Random(self.seed * 7919 + 1)
        hot = rng.sample(layout.pickups, 2)
        near = [p for p in layout.pickups
                if min(abs(layout.rc(p)[0] - layout.rc(h)[0]) + abs(layout.rc(p)[1] - layout.rc(h)[1]) for h in hot) <= 6]
        out: dict[int, list[tuple[int, bool]]] = {}
        t = rng.expovariate(self.order_rate)
        while t < self.horizon:
            pickup = rng.choice(near if rng.random() < self.hotspot_frac else layout.pickups)
            out.setdefault(int(t), []).append((pickup, rng.random() < self.urgent_frac))
            t += rng.expovariate(self.order_rate)
        return out

    def to_dict(self) -> dict:
        return {**asdict(self), "layout": asdict(self.layout)}


def with_faults(sc: Scenario, n_blocks: int = 2, n_failures: int = 1, block_duration: int = 150) -> Scenario:
    """Add seeded faults: blocked 3-cell segments of picking aisles, and robot failures."""
    rng = random.Random(sc.seed * 104729 + 3)
    layout = build(sc.layout)
    H, W = layout.shape
    g = layout.grid
    aisle_cols = [c for c in range(1, W - 1) if g[2, c] == FREE and (g[2, c - 1] == SHELF or g[2, c + 1] == SHELF)]
    faults = []
    for _ in range(n_blocks):
        col = rng.choice(aisle_cols)
        b = rng.randrange(sc.layout.n_block_rows)
        top = 2 + b * (sc.layout.block_len + 1)
        r0 = top + rng.randrange(0, max(1, sc.layout.block_len - 2))
        cells = [layout.cell(r, col) for r in range(r0, min(r0 + 3, top + sc.layout.block_len))]
        faults.append({"t": rng.randrange(sc.horizon // 5, sc.horizon // 2), "kind": "block",
                       "cells": cells, "duration": block_duration})
    for _ in range(n_failures):
        faults.append({"t": rng.randrange(sc.horizon // 4, 3 * sc.horizon // 4), "kind": "robot_fail",
                       "robot": rng.randrange(sc.n_robots)})
    sc.faults = sorted(faults, key=lambda f: f["t"])
    return sc
