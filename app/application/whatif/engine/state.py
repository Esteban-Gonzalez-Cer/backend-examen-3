"""Merge the live SII data (kardex + current enrollment) onto the curriculum graph."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.application.models import GradesPeriod, Kardex, Term, is_accredited
from app.application.whatif.engine.graph import CurriculumGraph


@dataclass
class ApprovedCourse:
    clave: str
    credits: int
    grade: float | None
    grade_label: str | None
    term_code: str


@dataclass
class InProgressCourse:
    clave: str
    name: str
    credits: int
    partial_average: float | None
    graded_partials: int


@dataclass
class StudentState:
    current_term: Term
    approved: dict[str, ApprovedCourse]
    in_progress: dict[str, InProgressCourse]
    failed_attempts: dict[str, int]
    approved_credits: int
    numeric_grades: list[float] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.upper().split())


def resolve_clave(graph: CurriculumGraph, clave: str, name: str) -> str | None:
    """Match by official code first, then by normalised subject name."""
    if clave in graph.subjects:
        return clave
    wanted = _normalize(name)
    for candidate, subject in graph.subjects.items():
        if _normalize(subject.name) == wanted:
            return candidate
    if "SERVICIO SOCIAL" in wanted:
        return next((c for c, s in graph.subjects.items() if "SERVICIO SOCIAL" in _normalize(s.name)), None)
    if "RESIDENCIA" in wanted:
        return next((c for c, s in graph.subjects.items() if "RESIDENCIA" in _normalize(s.name)), None)
    return None


def _current_term(kardex: Kardex, periods: list[GradesPeriod], today: datetime) -> Term:
    for period in periods:
        try:
            return Term.parse(period.term_code)
        except ValueError:
            continue
    terms = []
    for entry in kardex.entries:
        try:
            terms.append(Term.parse(entry.term_code))
        except ValueError:
            continue
    if terms:
        latest = max(terms)
        return latest.next(include_summer=False) if latest.is_summer or latest.kind == "2" else Term(latest.year, "2")
    return Term.from_date(today)


def build_student_state(
    graph: CurriculumGraph,
    kardex: Kardex,
    periods: list[GradesPeriod],
    today: datetime | None = None,
) -> StudentState:
    passing = graph.rules.passing_grade
    approved: dict[str, ApprovedCourse] = {}
    failed_attempts: dict[str, int] = {}
    approved_credits = 0
    numeric_grades: list[float] = []
    unmatched: list[str] = []

    for entry in kardex.entries:
        accredited = is_accredited(entry.grade, entry.grade_label, passing)
        clave = resolve_clave(graph, entry.clave, entry.name)
        if not accredited:
            key = clave or entry.clave
            failed_attempts[key] = failed_attempts.get(key, 0) + 1
            continue
        approved_credits += entry.credits
        if entry.grade is not None:
            numeric_grades.append(entry.grade)
        if clave is None:
            unmatched.append(entry.clave)
            continue
        approved[clave] = ApprovedCourse(
            clave=clave,
            credits=entry.credits,
            grade=entry.grade,
            grade_label=entry.grade_label,
            term_code=entry.term_code,
        )

    current_term = _current_term(kardex, periods, today or datetime.now(UTC))
    in_progress: dict[str, InProgressCourse] = {}
    for period in periods:
        if period.term_code != current_term.code:
            continue
        for course in period.courses:
            clave = resolve_clave(graph, course.clave, course.name)
            if clave is None:
                unmatched.append(course.clave)
                continue
            if clave in approved:
                continue
            graded = [p.grade for p in course.partials if p.grade is not None]
            in_progress[clave] = InProgressCourse(
                clave=clave,
                name=graph.subjects[clave].name,
                credits=graph.subjects[clave].credits,
                partial_average=round(sum(graded) / len(graded), 2) if graded else None,
                graded_partials=len(graded),
            )

    return StudentState(
        current_term=current_term,
        approved=approved,
        in_progress=in_progress,
        failed_attempts=failed_attempts,
        approved_credits=approved_credits,
        numeric_grades=numeric_grades,
        unmatched=unmatched,
    )
