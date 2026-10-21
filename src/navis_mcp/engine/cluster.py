"""Turn thousands of clashes into countable problems.

Two passes: clashes sharing the same pair of assemblies are one problem wherever
they sit; then clashes of one discipline pair that lie within ``eps`` of each other
are joined (single linkage on a uniform grid). Groups too large to walk to are bisected.
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import product

from ..model import Clash, Point, dist

_NEIGHBOURS = list(product((-1, 0, 1), repeat=3))


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def pair_key(c: Clash) -> tuple[str, str]:
    a, b = sorted((c.a.discipline, c.b.discipline))
    return a, b


def _span(points: list[Point]) -> tuple[float, int]:
    extents = [max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)]
    axis = max(range(3), key=lambda i: extents[i])
    return extents[axis], axis


def _bisect(group: list[Clash], max_span: float) -> list[list[Clash]]:
    if len(group) < 2:
        return [group]
    span, axis = _span([c.point for c in group])
    if span <= max_span:
        return [group]
    ordered = sorted(group, key=lambda c: (c.point[axis], c.id))
    mid = len(ordered) // 2
    return _bisect(ordered[:mid], max_span) + _bisect(ordered[mid:], max_span)


def cluster(clashes: list[Clash], eps: float, max_span: float) -> list[list[Clash]]:
    n = len(clashes)
    uf = _UnionFind(n)

    by_pair: dict[tuple[str, str], int] = {}
    grid: dict[tuple, list[int]] = defaultdict(list)
    cell = max(eps, 1e-6)
    for i, c in enumerate(clashes):
        key = tuple(sorted((c.a.key, c.b.key)))
        if key in by_pair:
            uf.union(i, by_pair[key])
        else:
            by_pair[key] = i
        pair = pair_key(c)
        cx, cy, cz = (math.floor(v / cell) for v in c.point)
        for dx, dy, dz in _NEIGHBOURS:
            for j in grid.get((pair, cx + dx, cy + dy, cz + dz), ()):
                if dist(c.point, clashes[j].point) <= eps:
                    uf.union(i, j)
        grid[(pair, cx, cy, cz)].append(i)

    groups: dict[int, list[Clash]] = defaultdict(list)
    for i, c in enumerate(clashes):
        groups[uf.find(i)].append(c)

    out: list[list[Clash]] = []
    for root in sorted(groups):
        out.extend(_bisect(groups[root], max_span))
    return out
