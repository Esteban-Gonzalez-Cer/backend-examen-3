"""Critical path, bottlenecks, credit gates and GPA on top of a projection."""

from __future__ import annotations

import math

from app.application.models import Term
from app.application.whatif.engine.graph import CurriculumGraph
from app.application.whatif.engine.projection import Projection
from app.application.whatif.engine.results import (
    Bottleneck,
    CriticalStep,
    GateMilestone,
    GpaProjection,
)
from app.application.whatif.engine.state import StudentState

# --------------------------------------------------------------------------- CPM


def compute_slack(graph: CurriculumGraph, pending: set[str]) -> dict[str, int]:
    """Structural CPM with unit durations (ignores load limits and credit gates)."""
    order = graph.topological_order(pending)
    earliest: dict[str, int] = {}
    for clave in order:
        value = 0
        for req in graph.prereqs[clave] & pending:
            value = max(value, earliest[req] + 1)
        for req in graph.coreqs[clave] & pending:
            value = max(value, earliest[req])
        earliest[clave] = value
    length = max((earliest[c] + 1 for c in order), default=0)
    latest: dict[str, int] = {}
    for clave in reversed(order):
        value = length - 1
        for succ in graph.successors[clave] & pending:
            value = min(value, latest[succ] - 1)
        for dep in graph.coreq_dependents[clave] & pending:
            value = min(value, latest[dep])
        latest[clave] = value
    return {c: latest[c] - earliest[c] for c in order}


# --------------------------------------------------------------------------- binding chain


def _explain(graph: CurriculumGraph, proj: Projection, clave: str) -> tuple[str, str | None, str]:
    subject = graph.subjects[clave]
    idx = proj.term_index[clave]
    if idx == 0:
        if clave in proj.retakes:
            return "retake", None, "Reprobada en el escenario: se recursa en el siguiente periodo."
        return "start", None, "Disponible desde el siguiente periodo."

    planned_prereqs = [(proj.term_index[p], p) for p in graph.prereqs[clave] if p in proj.term_index]
    if planned_prereqs:
        p_idx, prereq = max(planned_prereqs)
        if p_idx == idx - 1 or all(proj.plan[k].term.is_summer for k in range(p_idx + 1, idx)):
            return "prereq", prereq, f"Requiere {graph.subjects[prereq].name} aprobada antes."

    same_term_coreqs = [q for q in graph.coreqs[clave] if proj.term_index.get(q) == idx]
    if same_term_coreqs:
        coreq = sorted(same_term_coreqs)[0]
        return "coreq", coreq, f"Se cursa junto con su co-requisito {graph.subjects[coreq].name}."

    previous = proj.plan[idx - 1]
    until = proj.params.postpone.get(clave)
    if until:
        try:
            if previous.term < Term.parse(until):
                return "postponed", None, f"Pospuesta en el escenario hasta {Term.parse(until).label}."
        except ValueError:
            pass
    if subject.min_credit_pct is not None:
        pct = previous.credits_start * 100 / graph.total_credits
        if pct < subject.min_credit_pct:
            needed = math.ceil(subject.min_credit_pct * graph.total_credits / 100)
            return (
                "credit_gate",
                None,
                f"Necesita {subject.min_credit_pct:g}% de créditos ({needed}); en {previous.term.label} "
                f"tendrías {previous.credits_start}.",
            )
    if previous.term.is_summer:
        return "summer_rules", None, "El verano solo admite materias regulares y una carga reducida."
    return (
        "load_limit",
        None,
        f"No cupo en {previous.term.label} por el límite de {proj.max_credits} créditos.",
    )


def binding_chain(graph: CurriculumGraph, proj: Projection) -> list[CriticalStep]:
    """Walk back from graduation explaining why each step could not happen earlier."""
    if not proj.plan:
        return []
    best: list[CriticalStep] = []
    for start in proj.plan[-1].selected:
        steps: list[CriticalStep] = []
        visited: set[str] = set()
        node: str | None = start
        while node is not None and node not in visited:
            visited.add(node)
            reason, previous, detail = _explain(graph, proj, node)
            term = proj.plan[proj.term_index[node]].term
            steps.append(
                CriticalStep(
                    clave=node,
                    name=graph.subjects[node].name,
                    term=term.code,
                    term_label=term.label,
                    reason=reason,
                    detail=detail,
                )
            )
            node = previous
        if len(steps) > len(best):
            best = steps
    best.reverse()
    return best


# --------------------------------------------------------------------------- bottlenecks


def structural_bottlenecks(
    graph: CurriculumGraph, proj: Projection, slack: dict[str, int], limit: int = 6
) -> list[Bottleneck]:
    pending = proj.pending_after_current
    items: list[Bottleneck] = []
    for clave in pending:
        descendants = graph.descendants(clave, within=pending)
        node_slack = slack.get(clave)
        if not descendants and node_slack != 0:
            continue
        downstream = proj.downstream.get(clave, 0)
        factor = 1 + (1 / (1 + node_slack) if node_slack is not None else 0)
        parts = []
        if descendants:
            parts.append(f"Desbloquea {len(descendants)} materia(s) ({downstream} créditos)")
        if node_slack == 0:
            parts.append("está en la ruta crítica (holgura 0)")
        items.append(
            Bottleneck(
                clave=clave,
                name=graph.subjects[clave].name,
                kind="structural",
                score=round(downstream * factor + (1 if node_slack == 0 else 0), 1),
                descendants=len(descendants),
                downstream_credits=downstream,
                slack=node_slack,
                delay_terms=None,
                detail="; ".join(parts).capitalize() + ".",
            )
        )
    items.sort(key=lambda b: (-b.score, b.clave))
    return items[:limit]


def gate_milestones(graph: CurriculumGraph, proj: Projection, current_term: Term) -> list[GateMilestone]:
    by_pct: dict[float, list[str]] = {}
    for subject in graph.subjects.values():
        if subject.min_credit_pct is not None:
            by_pct.setdefault(subject.min_credit_pct, []).append(subject.name)

    milestones = []
    for pct in sorted(by_pct):
        needed = math.ceil(pct * graph.total_credits / 100)
        reached_now = proj.approved_credits_now >= needed
        projected: Term | None = None
        if proj.credits_after_current >= needed:
            projected = current_term
        else:
            for term_plan in proj.plan:
                if term_plan.credits_end >= needed:
                    projected = term_plan.term
                    break
        milestones.append(
            GateMilestone(
                pct=pct,
                credits_needed=needed,
                subjects=sorted(by_pct[pct]),
                reached_now=reached_now,
                projected_term=projected.code if projected else None,
                projected_label=projected.label if projected else None,
            )
        )
    return milestones


def gate_bottlenecks(graph: CurriculumGraph, proj: Projection) -> list[Bottleneck]:
    items = []
    pct_after = proj.credits_after_current * 100 / graph.total_credits
    for clave in proj.pending_after_current:
        subject = graph.subjects[clave]
        if subject.min_credit_pct is None or pct_after + 1e-9 >= subject.min_credit_pct:
            continue
        needed = math.ceil(subject.min_credit_pct * graph.total_credits / 100)
        items.append(
            Bottleneck(
                clave=clave,
                name=subject.name,
                kind="gate",
                score=round(needed - proj.credits_after_current, 1),
                descendants=len(graph.descendants(clave, within=proj.pending_after_current)),
                downstream_credits=proj.downstream.get(clave, 0),
                slack=None,
                delay_terms=None,
                detail=(
                    f"Requiere {subject.min_credit_pct:g}% de créditos ({needed}); al cerrar el periodo "
                    f"actual tendrías {proj.credits_after_current}."
                ),
            )
        )
    items.sort(key=lambda b: (-b.score, b.clave))
    return items


# --------------------------------------------------------------------------- GPA


def project_gpa(state: StudentState, proj: Projection) -> GpaProjection:
    current = round(sum(state.numeric_grades) / len(state.numeric_grades), 2) if state.numeric_grades else None
    values = list(state.numeric_grades)
    for clave in proj.passed_in_progress:
        course = state.in_progress.get(clave)
        if course is None:
            continue
        grade = proj.params.grades.get(clave, course.partial_average)
        if grade is not None:
            values.append(grade)
    projected = round(sum(values) / len(values), 2) if values else None
    return GpaProjection(current=current, projected=projected)
