"""Graph utilities for the analysis pipeline.

Currently: cycle detection on the post.parent_id forest. Used by
``src/pipeline/extract.py`` (which raises on the first cycle, for the
upstream-drugs recursion's fail-fast guard) and conceptually duplicated
in ``docs/RCT_historical_validation/verify.py`` (which returns all
cycles, for audit-report purposes; that copy is kept inline to preserve
the reproducibility package's self-containment).
"""
from __future__ import annotations

from typing import Hashable, Mapping


def find_parent_cycles(
    parent_map: Mapping[Hashable, Hashable | None],
) -> list[list[Hashable]]:
    """Return every cycle in a parent-map (forest with possibly back-edges).

    Iterative DFS with white/gray/black coloring; O(N). Each returned
    list is a single cycle as a sequence of nodes ending with the node
    that closes the cycle (so ``[a, b, c, a]`` for the cycle a→b→c→a).
    Returns an empty list if the graph is a clean forest.

    Use cases:

    - Fail-fast guard before recursive traversal:
      ``cycles = find_parent_cycles(parent_map)``
      ``if cycles: raise ValueError("cycle: " + " -> ".join(cycles[0]))``
    - Audit report listing every cycle present in the data.
    """
    UNVISITED, VISITING, DONE = 0, 1, 2
    color: dict[Hashable, int] = {}
    cycles: list[list[Hashable]] = []
    for start in parent_map:
        if color.get(start, UNVISITED) != UNVISITED:
            continue
        stack: list[Hashable] = [start]
        path: list[Hashable] = []
        while stack:
            node = stack[-1]
            c = color.get(node, UNVISITED)
            if c == UNVISITED:
                color[node] = VISITING
                path.append(node)
                parent = parent_map.get(node)
                if parent is not None and parent in parent_map:
                    pcol = color.get(parent, UNVISITED)
                    if pcol == VISITING:
                        # back-edge into the active path -> cycle
                        i = path.index(parent)
                        cycles.append(path[i:] + [parent])
                        color[node] = DONE
                        if path and path[-1] == node:
                            path.pop()
                        stack.pop()
                        continue
                    if pcol == UNVISITED:
                        stack.append(parent)
                        continue
                # parent missing, NULL, or already DONE -> this node is finished
                color[node] = DONE
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
            else:
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
                color[node] = DONE
    return cycles
