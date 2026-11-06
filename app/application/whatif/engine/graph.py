"""The curriculum as a directed acyclic graph (edges point from requirement to dependent)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property

from app.application.models import Curriculum, CurriculumRules, Subject

SERVICIO_SOCIAL = "SS-0001"
RESIDENCIAS = "RP-0001"
ACTIVIDADES_COMPLEMENTARIAS = "ACT-0000"


@dataclass
class CurriculumGraph:
    subjects: dict[str, Subject]
    prereqs: dict[str, set[str]]  # node -> what must be approved in an earlier term
    coreqs: dict[str, set[str]]  # node -> what must be approved before or taken in the same term
    total_credits: int
    rules: CurriculumRules = field(default_factory=CurriculumRules)

    @classmethod
    def from_curriculum(cls, curriculum: Curriculum) -> CurriculumGraph:
        subjects = {s.clave: s for s in curriculum.subjects}
        prereqs: dict[str, set[str]] = {c: set() for c in subjects}
        coreqs: dict[str, set[str]] = {c: set() for c in subjects}
        for req in curriculum.requisites:
            if req.subject_clave not in subjects or req.requires_clave not in subjects:
                continue
            target = prereqs if req.type == "prereq" else coreqs
            target[req.subject_clave].add(req.requires_clave)
        return cls(
            subjects=subjects,
            prereqs=prereqs,
            coreqs=coreqs,
            total_credits=curriculum.total_credits,
            rules=curriculum.rules,
        )

    @cached_property
    def successors(self) -> dict[str, set[str]]:
        """node -> nodes that list it as a prerequisite."""
        result: dict[str, set[str]] = {c: set() for c in self.subjects}
        for node, reqs in self.prereqs.items():
            for req in reqs:
                result[req].add(node)
        return result

    @cached_property
    def coreq_dependents(self) -> dict[str, set[str]]:
        """node -> nodes that list it as a co-requisite."""
        result: dict[str, set[str]] = {c: set() for c in self.subjects}
        for node, reqs in self.coreqs.items():
            for req in reqs:
                result[req].add(node)
        return result

    def dependents(self, clave: str) -> set[str]:
        return self.successors[clave] | self.coreq_dependents[clave]

    def descendants(self, clave: str, within: set[str] | None = None) -> set[str]:
        seen: set[str] = set()
        stack = [clave]
        while stack:
            for nxt in self.dependents(stack.pop()):
                if nxt in seen or (within is not None and nxt not in within):
                    continue
                seen.add(nxt)
                stack.append(nxt)
        return seen

    def topological_order(self, nodes: set[str] | None = None) -> list[str]:
        nodes = set(self.subjects) if nodes is None else nodes
        indegree = {
            n: len((self.prereqs[n] | self.coreqs[n]) & nodes) for n in nodes
        }
        ready = sorted(n for n, d in indegree.items() if d == 0)
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for nxt in sorted(self.dependents(node) & nodes):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
        return order


def find_cycle(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> list[str] | None:
    """Return one cycle as a list of nodes (first == last) or None. Edges are (from, to)."""
    graph: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)
        graph.setdefault(dst, [])

    white, grey, black = 0, 1, 2
    color = dict.fromkeys(graph, white)
    parent: dict[str, str] = {}

    for start in sorted(graph):
        if color[start] != white:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = grey
        while stack:
            node, index = stack[-1]
            neighbours = graph[node]
            if index < len(neighbours):
                stack[-1] = (node, index + 1)
                nxt = neighbours[index]
                if color[nxt] == white:
                    parent[nxt] = node
                    color[nxt] = grey
                    stack.append((nxt, 0))
                elif color[nxt] == grey:
                    cycle = [nxt, node]
                    while cycle[-1] != nxt:
                        cycle.append(parent[cycle[-1]])
                    cycle.reverse()
                    return cycle
            else:
                color[node] = black
                stack.pop()
    return None
