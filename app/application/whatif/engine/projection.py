"""Term-by-term projection (list scheduling) of the remaining curriculum."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.application.models import Term
from app.application.whatif.engine.graph import SERVICIO_SOCIAL, CurriculumGraph
from app.application.whatif.engine.params import ScenarioParams
from app.application.whatif.engine.state import StudentState

MAX_TERMS = 24
_EPS = 1e-9


@dataclass
class TermPlan:
    term: Term
    selected: list[str]
    load: int
    credits_start: int
    credits_end: int


@dataclass
class Projection:
    params: ScenarioParams
    max_credits: int
    approved_now: set[str]
    approved_credits_now: int
    passed_in_progress: set[str]
    failed_in_progress: set[str]
    credits_after_current: int
    pending_after_current: set[str]
    available_first: set[str]
    tails: dict[str, int]
    downstream: dict[str, int]
    plan: list[TermPlan] = field(default_factory=list)
    term_index: dict[str, int] = field(default_factory=dict)
    unreachable: set[str] = field(default_factory=set)
    graduation_term: Term | None = None

    @property
    def retakes(self) -> set[str]:
        return self.failed_in_progress


def resolve_outcome(clave: str, params: ScenarioParams, passing_grade: float) -> str:
    explicit = params.outcomes.get(clave)
    if explicit in ("pass", "fail"):
        return explicit
    if clave in params.grades:
        return "pass" if params.grades[clave] >= passing_grade else "fail"
    return "pass"


def compute_priorities(graph: CurriculumGraph, pending: set[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Tail = longest chain of pending terms that hangs from a node (itself included)."""
    tails: dict[str, int] = {}
    for clave in reversed(graph.topological_order(pending)):
        tail = 1
        for succ in graph.successors[clave] & pending:
            tail = max(tail, 1 + tails.get(succ, 1))
        for dep in graph.coreq_dependents[clave] & pending:
            tail = max(tail, tails.get(dep, 1))
        tails[clave] = tail
    for clave in pending:
        tails.setdefault(clave, 1)
    downstream = {
        clave: sum(graph.subjects[d].credits for d in graph.descendants(clave, within=pending))
        for clave in pending
    }
    return tails, downstream


class _Scheduler:
    def __init__(self, graph: CurriculumGraph, params: ScenarioParams, max_credits: int, priority) -> None:  # type: ignore[no-untyped-def]
        self.graph = graph
        self.params = params
        self.max_credits = max_credits
        self.priority = priority
        self._postpone = {}
        for clave, code in params.postpone.items():
            try:
                self._postpone[clave] = Term.parse(code)
            except ValueError:
                continue

    def postponed_until(self, clave: str) -> Term | None:
        return self._postpone.get(clave)

    def eligible(self, clave: str, term: Term, credits_start: int, done: set[str]) -> bool:
        subject = self.graph.subjects[clave]
        if not self.graph.prereqs[clave] <= done:
            return False
        if subject.min_credit_pct is not None:
            pct = credits_start * 100 / self.graph.total_credits
            if pct + _EPS < subject.min_credit_pct:
                return False
        until = self._postpone.get(clave)
        if until is not None and term < until:
            return False
        return not (term.is_summer and subject.kind == "special_requirement")

    def _bundle(
        self, clave: str, chosen: set[str], done: set[str], eligible: set[str], visiting: set[str]
    ) -> list[str] | None:
        bundle = [clave]
        for req in sorted(self.graph.coreqs[clave]):
            if req in done or req in chosen or req in visiting:
                continue
            if req not in eligible:
                return None
            visiting.add(req)
            sub = self._bundle(req, chosen, done, eligible, visiting)
            if sub is None:
                return None
            bundle.extend(x for x in sub if x not in bundle)
        return bundle

    def select(self, term: Term, credits_start: int, done: set[str], pending: set[str]) -> tuple[list[str], int, set[str]]:
        eligible = {c for c in pending if self.eligible(c, term, credits_start, done)}
        chosen: set[str] = set()
        selected: list[str] = []
        load = 0
        count = 0
        summer_cap = self.graph.rules.summer_max_subjects
        for clave in sorted(eligible, key=self.priority):
            if clave in chosen:
                continue
            bundle = self._bundle(clave, chosen, done, eligible, {clave})
            if bundle is None:
                continue
            counted = [b for b in bundle if self.graph.subjects[b].counts_toward_load]
            add_load = sum(self.graph.subjects[b].credits for b in counted)
            if term.is_summer:
                if count + len(counted) > summer_cap:
                    continue
            elif load + add_load > self.max_credits:
                continue
            for b in bundle:
                chosen.add(b)
                selected.append(b)
            load += add_load
            count += len(counted)
        return selected, load, eligible


def project(graph: CurriculumGraph, state: StudentState, params: ScenarioParams) -> Projection:
    rules = graph.rules
    max_credits = params.max_credits_per_term or rules.max_credits_per_term

    approved_now = set(state.approved)
    approved_credits_now = state.approved_credits
    passed: set[str] = set()
    failed: set[str] = set()
    for clave in state.in_progress:
        if resolve_outcome(clave, params, rules.passing_grade) == "pass":
            passed.add(clave)
        else:
            failed.add(clave)

    if SERVICIO_SOCIAL in graph.subjects and SERVICIO_SOCIAL not in approved_now | set(state.in_progress):
        if params.servicio_social == "done":
            approved_now.add(SERVICIO_SOCIAL)
            approved_credits_now += graph.subjects[SERVICIO_SOCIAL].credits
        elif params.servicio_social == "in_progress":
            passed.add(SERVICIO_SOCIAL)

    done = approved_now | passed
    credits = approved_credits_now + sum(graph.subjects[c].credits for c in passed)
    pending = set(graph.subjects) - done
    tails, downstream = compute_priorities(graph, pending)

    def priority(clave: str) -> tuple:
        return (
            0 if clave in failed else 1,
            -tails[clave],
            -downstream[clave],
            graph.subjects[clave].suggested_semester,
            clave,
        )

    scheduler = _Scheduler(graph, params, max_credits, priority)
    projection = Projection(
        params=params,
        max_credits=max_credits,
        approved_now=approved_now,
        approved_credits_now=approved_credits_now,
        passed_in_progress=passed,
        failed_in_progress=failed,
        credits_after_current=credits,
        pending_after_current=set(pending),
        available_first=set(),
        tails=tails,
        downstream=downstream,
    )

    term = state.current_term.next(params.include_summer)
    empty_streak = 0
    for index in range(MAX_TERMS):
        if not pending:
            break
        selected, load, eligible = scheduler.select(term, credits, done, pending)
        if index == 0:
            projection.available_first = eligible
        start = credits
        for clave in selected:
            done.add(clave)
            pending.discard(clave)
            credits += graph.subjects[clave].credits
        projection.plan.append(TermPlan(term, selected, load, start, credits))

        if selected:
            empty_streak = 0
        else:
            waiting_on_postpone = any(
                (until := scheduler.postponed_until(c)) is not None and term < until for c in pending
            )
            empty_streak = 0 if waiting_on_postpone else empty_streak + 1
            if empty_streak >= 3:
                break
        term = term.next(params.include_summer)

    while projection.plan and not projection.plan[-1].selected:
        projection.plan.pop()
    for idx, term_plan in enumerate(projection.plan):
        for clave in term_plan.selected:
            projection.term_index[clave] = idx

    projection.unreachable = pending
    if pending:
        projection.graduation_term = None
    elif projection.plan:
        projection.graduation_term = projection.plan[-1].term
    else:
        projection.graduation_term = state.current_term
    return projection
