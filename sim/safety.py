"""Execution safety layer: the last line of defence between plans and motion.

Given current cells and proposed next cells, cancels (turns into a wait) every move that would
enter a non-passable cell, jump more than one cell, create a vertex conflict (two robots in one
cell) or an edge conflict (two robots swapping cells). Cancellations can cascade (a robot following
into a cell whose occupant now stays), so it iterates to a fixed point. It then asserts that the
result is collision-free, so a collision can never be executed silently.
"""

from __future__ import annotations

from collections import defaultdict


class CollisionError(AssertionError):
    pass


def resolve(cur: dict[int, int], proposed: dict[int, int], grid) -> tuple[dict[int, int], set[int]]:
    final = dict(proposed)
    cancelled: set[int] = set()

    def stay(rid: int) -> None:
        final[rid] = cur[rid]
        cancelled.add(rid)

    for rid, nxt in proposed.items():
        if nxt != cur[rid] and (nxt not in grid.adj[cur[rid]] or not grid.passable(nxt)):
            stay(rid)
    at = {c: rid for rid, c in cur.items()}
    changed = True
    while changed:
        changed = False
        for rid in sorted(final):
            a, b = cur[rid], final[rid]
            other = at.get(b)
            if a != b and other is not None and other != rid and final[other] == a:  # swap
                stay(rid)
                stay(other)
                changed = True
        groups = defaultdict(list)
        for rid, c in final.items():
            groups[c].append(rid)
        for c, rids in groups.items():
            if len(rids) > 1:  # vertex conflict: a robot already standing there wins, else lowest id
                keep = next((r for r in rids if cur[r] == c), min(rids))
                for r in rids:
                    if r != keep:
                        stay(r)
                changed = True
    check(cur, final)
    return final, cancelled


def check(cur: dict[int, int], final: dict[int, int]) -> None:
    cells = list(final.values())
    if len(cells) != len(set(cells)):
        raise CollisionError(f"vertex collision: {final}")
    at = {c: rid for rid, c in cur.items()}
    for rid, b in final.items():
        other = at.get(b)
        if other is not None and other != rid and cur[rid] != b and final[other] == cur[rid]:
            raise CollisionError(f"edge-swap collision between {rid} and {other}")
