"""Entry point of the What-If engine: project, analyse and package a scenario."""

from __future__ import annotations

from dataclasses import replace

from app.application.models import Term
from app.application.whatif.engine.analysis import (
    binding_chain,
    compute_slack,
    gate_bottlenecks,
    gate_milestones,
    project_gpa,
    structural_bottlenecks,
)
from app.application.whatif.engine.graph import CurriculumGraph
from app.application.whatif.engine.params import ScenarioParams
from app.application.whatif.engine.projection import Projection, project
from app.application.whatif.engine.results import (
    Bottleneck,
    CreditSummary,
    EdgeView,
    FailureImpact,
    NodeView,
    PlannedSubject,
    PlannedTerm,
    RulesView,
    SimulationResult,
)
from app.application.whatif.engine.state import StudentState


def graduation_delay(base: Term | None, other: Term | None) -> int | None:
    if base is None or other is None:
        return None
    return other.semester_index - base.semester_index


def failure_impacts(
    graph: CurriculumGraph, state: StudentState, params: ScenarioParams, base: Projection
) -> list[FailureImpact]:
    impacts: list[FailureImpact] = []

    for clave in sorted(base.passed_in_progress & set(state.in_progress)):
        grades = {k: v for k, v in params.grades.items() if k != clave}
        trial = project(graph, state, replace(params, outcomes={**params.outcomes, clave: "fail"}, grades=grades))
        impacts.append(_impact(graph, clave, "fail", base, trial))

    if base.plan:
        first = base.plan[0]
        later = first.term.next(params.include_summer)
        for clave in first.selected:
            if clave in base.retakes:
                continue
            trial = project(graph, state, replace(params, postpone={**params.postpone, clave: later.code}))
            impacts.append(_impact(graph, clave, "postpone", base, trial))

    impacts.sort(key=lambda i: (-(i.delay_terms if i.delay_terms is not None else 99), i.clave))
    return impacts


def _impact(graph: CurriculumGraph, clave: str, scenario: str, base: Projection, trial: Projection) -> FailureImpact:
    grad = trial.graduation_term
    return FailureImpact(
        clave=clave,
        name=graph.subjects[clave].name,
        scenario=scenario,
        delay_terms=graduation_delay(base.graduation_term, grad) if grad else None,
        new_graduation_term=grad.code if grad else None,
        new_graduation_label=grad.label if grad else None,
    )


def simulate(
    graph: CurriculumGraph,
    state: StudentState,
    params: ScenarioParams,
    *,
    with_sensitivity: bool = True,
) -> SimulationResult:
    proj = project(graph, state, params)
    slack = compute_slack(graph, proj.pending_after_current)
    chain = binding_chain(graph, proj)
    chain_claves = {step.clave for step in chain}
    critical_pairs = {
        (chain[i].clave, chain[i + 1].clave)
        for i in range(len(chain) - 1)
        if chain[i + 1].reason in ("prereq", "coreq")
    }

    impacts = failure_impacts(graph, state, params, proj) if with_sensitivity else []
    hidden = [
        Bottleneck(
            clave=i.clave,
            name=i.name,
            kind="hidden",
            score=float(100 * (i.delay_terms or 0) if i.delay_terms is not None else 999),
            descendants=len(graph.descendants(i.clave, within=proj.pending_after_current)),
            downstream_credits=proj.downstream.get(i.clave, 0),
            slack=slack.get(i.clave),
            delay_terms=i.delay_terms,
            detail=(
                f"{'Reprobarla' if i.scenario == 'fail' else 'Posponerla un periodo'} retrasaría tu egreso "
                + (f"{i.delay_terms} semestre(s)." if i.delay_terms is not None else "indefinidamente.")
            ),
        )
        for i in impacts
        if i.delay_terms is None or i.delay_terms > 0
    ]
    # One entry per subject: the most actionable kind wins (hidden > gate > structural).
    bottlenecks: list[Bottleneck] = []
    for item in hidden + gate_bottlenecks(graph, proj) + structural_bottlenecks(graph, proj, slack):
        if all(b.clave != item.clave for b in bottlenecks):
            bottlenecks.append(item)

    plan = [
        PlannedTerm(
            term=tp.term.code,
            label=tp.term.label,
            is_summer=tp.term.is_summer,
            load_credits=tp.load,
            credits_after=tp.credits_end,
            subjects=[
                PlannedSubject(
                    clave=c,
                    name=graph.subjects[c].name,
                    credits=graph.subjects[c].credits,
                    is_retake=c in proj.retakes,
                    counts_toward_load=graph.subjects[c].counts_toward_load,
                )
                for c in tp.selected
            ],
        )
        for tp in proj.plan
    ]

    nodes = []
    for clave, subject in graph.subjects.items():
        planned_idx = proj.term_index.get(clave)
        planned = proj.plan[planned_idx].term if planned_idx is not None else None
        approved = state.approved.get(clave)
        if clave in proj.approved_now:
            status = "approved"
        elif clave in proj.passed_in_progress:
            status = "in_progress"
        elif clave in proj.failed_in_progress:
            status = "failed_sim"
        elif clave in proj.available_first:
            status = "available"
        elif planned is not None:
            status = "planned"
        else:
            status = "unreachable"
        nodes.append(
            NodeView(
                clave=clave,
                name=subject.name,
                credits=subject.credits,
                suggested_semester=subject.suggested_semester,
                grid_row=subject.grid_row,
                grid_col=subject.grid_col,
                kind=subject.kind,
                status=status,
                grade_label=approved.grade_label if approved else None,
                planned_term=planned.code if planned else None,
                planned_label=planned.label if planned else None,
                min_credit_pct=subject.min_credit_pct,
                on_critical_path=clave in chain_claves,
                slack=slack.get(clave),
            )
        )

    edges = [
        EdgeView(source=req, target=clave, type=kind, critical=(req, clave) in critical_pairs)
        for kind, mapping in (("prereq", graph.prereqs), ("coreq", graph.coreqs))
        for clave, reqs in mapping.items()
        for req in sorted(reqs)
    ]

    warnings = _warnings(graph, state, proj)
    in_progress_credits = sum(c.credits for c in state.in_progress.values())
    total = graph.total_credits
    grad = proj.graduation_term
    return SimulationResult(
        current_term=state.current_term.code,
        current_term_label=state.current_term.label,
        projected_graduation_term=grad.code if grad else None,
        projected_graduation_label=grad.label if grad else None,
        terms_remaining=len(proj.plan) if grad else None,
        delta_vs_baseline=None,
        credits=CreditSummary(
            approved=proj.approved_credits_now,
            in_progress=in_progress_credits,
            after_current_term=proj.credits_after_current,
            total=total,
            approved_pct=round(proj.approved_credits_now * 100 / total, 2),
            after_current_pct=round(proj.credits_after_current * 100 / total, 2),
        ),
        plan=plan,
        critical_path=chain,
        bottlenecks=bottlenecks,
        failure_impact=impacts,
        gates=gate_milestones(graph, proj, state.current_term),
        gpa=project_gpa(state, proj),
        nodes=nodes,
        edges=edges,
        warnings=warnings,
        unreachable=sorted(proj.unreachable),
        rules=RulesView(
            max_credits_per_term=graph.rules.max_credits_per_term,
            min_credits_per_term=graph.rules.min_credits_per_term,
            summer_max_subjects=graph.rules.summer_max_subjects,
            passing_grade=graph.rules.passing_grade,
        ),
    )


def _warnings(graph: CurriculumGraph, state: StudentState, proj: Projection) -> list[str]:
    warnings = []
    if proj.max_credits < graph.rules.min_credits_per_term:
        warnings.append(
            f"La carga máxima elegida ({proj.max_credits}) es menor a la carga mínima "
            f"reglamentaria ({graph.rules.min_credits_per_term} créditos)."
        )
    for clave in sorted(proj.failed_in_progress):
        if state.failed_attempts.get(clave, 0) >= 1:
            warnings.append(
                f"{graph.subjects[clave].name} ya fue reprobada antes: reprobarla de nuevo implica curso especial."
            )
    if proj.unreachable:
        names = ", ".join(graph.subjects[c].name for c in sorted(proj.unreachable))
        warnings.append(f"No fue posible programar: {names}. Revisa requisitos o posposiciones.")
    if state.unmatched:
        warnings.append(
            "Materias del SII que no están en la retícula cargada: " + ", ".join(sorted(set(state.unmatched))) + "."
        )
    return warnings
