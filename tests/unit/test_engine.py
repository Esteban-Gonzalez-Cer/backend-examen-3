from app.application.models import Curriculum, CurriculumRules, Requisite, Subject, Term
from app.application.whatif.engine.graph import CurriculumGraph, find_cycle
from app.application.whatif.engine.params import ScenarioParams
from app.application.whatif.engine.projection import project
from app.application.whatif.engine.simulator import simulate
from app.application.whatif.engine.state import build_student_state

# --------------------------------------------------------------------------- curriculum seed


def test_seed_totals_match_the_reticula(curriculum):
    assert sum(s.credits for s in curriculum.subjects) == 260
    assert curriculum.total_credits == 260
    assert len(curriculum.subjects) == 54


def test_seed_contains_every_verified_edge(graph):
    assert graph.prereqs["SCC-1010"] == {"ACF-0903", "AED-1026"}
    assert graph.prereqs["SCA-1002"] == {"SCD-1004", "SCA-1026"}
    assert graph.prereqs["SCG-1009"] == {"SCD-1011", "SCA-1025"}
    assert graph.prereqs["SCC-1019"] == {"AED-1026"}
    assert graph.prereqs["IDD-2504"] == {"AEB-1055"}
    assert graph.prereqs["ACF-0903"] == {"ACF-2301"}
    assert graph.prereqs["SCD-1022"] == {"SCC-1013"}
    assert graph.prereqs["SCC-1013"] == {"AEF-1052"}
    assert graph.prereqs["AEB-1055"] == {"SCA-1025"}
    assert graph.prereqs["RP-0001"] == {"SS-0001", "ACT-0000"}
    for clave in ("IDD-2501", "IDD-2503", "IDD-2502", "IDF-2505"):
        assert graph.prereqs[clave] == set()
    assert graph.coreqs["IDF-2505"] == {"IDD-2501"}
    assert graph.coreqs["IDD-2502"] == {"SCA-1002"}
    assert graph.coreqs["AEF-1052"] == {"ACF-0902"}


def test_seed_is_acyclic(curriculum):
    edges = [(r.requires_clave, r.subject_clave) for r in curriculum.requisites]
    assert find_cycle([s.clave for s in curriculum.subjects], edges) is None


def test_find_cycle_reports_the_loop():
    cycle = find_cycle(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"A", "B", "C"}


# --------------------------------------------------------------------------- student state


def test_state_from_real_kardex(state):
    assert state.current_term == Term.parse("26/2")
    assert len(state.approved) == 44
    assert state.approved_credits == 203
    assert set(state.in_progress) == {"IDD-2502", "SCG-1009", "IDD-2504", "IDD-2503", "SCA-1002", "ACA-0909"}
    assert sum(c.credits for c in state.in_progress.values()) == 29
    assert state.in_progress["IDD-2503"].partial_average == 75
    assert not state.unmatched


# --------------------------------------------------------------------------- projection


def test_baseline_projection(graph, state):
    result = simulate(graph, state, ScenarioParams())
    assert result.credits.approved == 203
    assert result.credits.approved_pct == 78.08
    assert result.credits.after_current_term == 232
    assert [p.term for p in result.plan] == ["27/1", "27/2"]
    assert {s.clave for s in result.plan[0].subjects} == {"SCD-1023", "ACA-0910", "SS-0001"}
    assert [s.clave for s in result.plan[1].subjects] == ["RP-0001"]
    assert result.projected_graduation_term == "27/2"
    assert result.terms_remaining == 2
    assert result.gpa.current == 92.21
    assert not result.unreachable


def test_critical_path_runs_through_servicio_social(graph, state):
    result = simulate(graph, state, ScenarioParams())
    assert [s.clave for s in result.critical_path] == ["SS-0001", "RP-0001"]
    assert result.critical_path[-1].reason == "prereq"
    critical_edges = {(e.source, e.target) for e in result.edges if e.critical}
    assert critical_edges == {("SS-0001", "RP-0001")}


def test_servicio_social_is_the_hidden_bottleneck(graph, state):
    result = simulate(graph, state, ScenarioParams())
    hidden = [b for b in result.bottlenecks if b.kind == "hidden"]
    assert [b.clave for b in hidden] == ["SS-0001"]
    assert hidden[0].delay_terms == 1
    impacts = {(i.clave, i.scenario): i.delay_terms for i in result.failure_impact}
    assert impacts[("ACA-0909", "fail")] == 0
    assert impacts[("IDD-2503", "fail")] == 0


def test_starting_servicio_social_now_saves_a_semester(graph, state):
    result = simulate(graph, state, ScenarioParams(servicio_social="in_progress"))
    assert result.projected_graduation_term == "27/1"
    assert {s.clave for s in result.plan[0].subjects} == {"SCD-1023", "ACA-0910", "RP-0001"}


def test_failing_taller_investigacion_moves_part_two(graph, state):
    result = simulate(graph, state, ScenarioParams(outcomes={"ACA-0909": "fail"}))
    plan = {s.clave: p.term for p in result.plan for s in p.subjects}
    assert plan["ACA-0909"] == "27/1"
    assert plan["ACA-0910"] == "27/2"
    assert result.projected_graduation_term == "27/2"
    node = next(n for n in result.nodes if n.clave == "ACA-0909")
    assert node.status == "failed_sim"


def test_low_grade_implies_failure(graph, state):
    result = simulate(graph, state, ScenarioParams(grades={"IDD-2503": 60}))
    node = next(n for n in result.nodes if n.clave == "IDD-2503")
    assert node.status == "failed_sim"


def test_load_limit_pushes_subjects_later(graph, state):
    result = simulate(graph, state, ScenarioParams(max_credits_per_term=4))
    first = {s.clave for s in result.plan[0].subjects if s.counts_toward_load}
    assert len(first) == 1
    assert any("carga mínima" in w for w in result.warnings)


def test_postpone_is_respected(graph, state):
    result = simulate(graph, state, ScenarioParams(postpone={"SCD-1023": "28/1"}))
    plan = {s.clave: p.term for p in result.plan for s in p.subjects}
    assert plan["SCD-1023"] == "28/1"
    assert result.projected_graduation_term == "28/1"


# --------------------------------------------------------------------------- synthetic graphs


def _tiny_curriculum(requisites, subjects=None, total=20) -> Curriculum:
    subjects = subjects or [
        Subject(clave=c, name=c, credits=5, ht=2, hp=3, suggested_semester=i + 1, grid_row=1, grid_col=i + 1)
        for i, c in enumerate(["A", "B", "C", "D"])
    ]
    return Curriculum(
        id=1, code="T", specialty_code=None, name="T", total_credits=total,
        subjects=subjects, requisites=requisites, rules=CurriculumRules(max_credits_per_term=10),
    )


def _empty_state(graph):
    from app.application.models import Kardex

    state = build_student_state(graph, Kardex(progress_pct=0, entries=[]), [])
    return state.__class__(**{**state.__dict__, "current_term": Term.parse("26/2")})


def test_coreqs_are_scheduled_together():
    curriculum = _tiny_curriculum([Requisite("B", "A", "coreq"), Requisite("C", "B", "prereq")])
    graph = CurriculumGraph.from_curriculum(curriculum)
    proj = project(graph, _empty_state(graph), ScenarioParams())
    first = set(proj.plan[0].selected)
    assert {"A", "B"} <= first


def test_credit_gate_blocks_until_reached():
    subjects = [
        Subject(clave="A", name="A", credits=10, ht=0, hp=0, suggested_semester=1, grid_row=1, grid_col=1),
        Subject(clave="G", name="G", credits=5, ht=0, hp=0, suggested_semester=2, grid_row=1, grid_col=2,
                min_credit_pct=50),
    ]
    graph = CurriculumGraph.from_curriculum(_tiny_curriculum([], subjects=subjects, total=20))
    result = simulate(graph, _empty_state(graph), ScenarioParams())
    plan = {s.clave: p.term for p in result.plan for s in p.subjects}
    assert plan == {"A": "27/1", "G": "27/2"}
    assert result.critical_path[-1].reason == "credit_gate"
