"""Use cases for the four SII-backed views: profile, grades, kardex and schedule."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.application.models import (
    PASSING_GRADE_DEFAULT,
    AuthenticatedSession,
    KardexEntry,
    PartialGrade,
    ScheduledCourse,
    StudentProfile,
    Term,
    grade_level,
    is_accredited,
)
from app.application.ports import SessionRepository, SiiGateway
from app.application.services.sii_guard import guarded

# --------------------------------------------------------------------------- view models


@dataclass
class CourseGradesView:
    group_id: int
    clave: str
    name: str
    group_letter: str
    partials: list[PartialGrade]
    graded_count: int
    average: float | None
    final: float | None
    level: str


@dataclass
class GradesPeriodView:
    term_code: str
    term_label: str
    year: int
    description: str
    average: float | None
    courses: list[CourseGradesView]


@dataclass
class SchedulePeriodView:
    term_code: str
    term_label: str
    year: int
    description: str
    courses: list[ScheduledCourse]


@dataclass
class KardexEntryView:
    clave: str
    name: str
    term_code: str
    term_label: str
    credits: int
    grade: float | None
    grade_label: str | None
    accredited: bool
    level: str
    description: str
    semester: int


@dataclass
class KardexSemesterView:
    semester: int
    credits: int
    average: float | None
    entries: list[KardexEntryView]


@dataclass
class KardexView:
    progress_pct: float
    accredited_credits: int
    average: float | None
    approved_count: int
    failed_count: int
    semesters: list[KardexSemesterView]


def _term_label(code: str) -> str:
    try:
        return Term.parse(code).label
    except ValueError:
        return code


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build_grades_view(periods) -> list[GradesPeriodView]:  # type: ignore[no-untyped-def]
    result = []
    for period in periods:
        courses = []
        for course in period.courses:
            graded = [p.grade for p in course.partials if p.grade is not None]
            average = _mean(graded)
            complete = bool(course.partials) and len(graded) == len(course.partials)
            courses.append(
                CourseGradesView(
                    group_id=course.group_id,
                    clave=course.clave,
                    name=course.name,
                    group_letter=course.group_letter,
                    partials=course.partials,
                    graded_count=len(graded),
                    average=average,
                    final=average if complete else None,
                    level=grade_level(average),
                )
            )
        averages = [c.average for c in courses if c.average is not None]
        result.append(
            GradesPeriodView(
                term_code=period.term_code,
                term_label=_term_label(period.term_code),
                year=period.year,
                description=period.description,
                average=_mean(averages),
                courses=courses,
            )
        )
    return result


def build_kardex_view(progress_pct: float, entries: list[KardexEntry]) -> KardexView:
    by_semester: dict[int, list[KardexEntryView]] = defaultdict(list)
    for entry in entries:
        accredited = is_accredited(entry.grade, entry.grade_label, PASSING_GRADE_DEFAULT)
        by_semester[entry.semester].append(
            KardexEntryView(
                clave=entry.clave,
                name=entry.name,
                term_code=entry.term_code,
                term_label=_term_label(entry.term_code),
                credits=entry.credits,
                grade=entry.grade,
                grade_label=entry.grade_label,
                accredited=accredited,
                level=grade_level(entry.grade) if entry.grade is not None else ("good" if accredited else "none"),
                description=entry.description,
                semester=entry.semester,
            )
        )

    semesters = []
    for number in sorted(by_semester):
        items = by_semester[number]
        numeric = [e.grade for e in items if e.accredited and e.grade is not None]
        semesters.append(
            KardexSemesterView(
                semester=number,
                credits=sum(e.credits for e in items if e.accredited),
                average=_mean(numeric),
                entries=items,
            )
        )

    all_items = [e for s in semesters for e in s.entries]
    numeric_all = [e.grade for e in all_items if e.accredited and e.grade is not None]
    return KardexView(
        progress_pct=progress_pct,
        accredited_credits=sum(e.credits for e in all_items if e.accredited),
        average=_mean(numeric_all),
        approved_count=sum(1 for e in all_items if e.accredited),
        failed_count=sum(1 for e in all_items if not e.accredited),
        semesters=semesters,
    )


class AcademicService:
    def __init__(self, sii: SiiGateway, sessions: SessionRepository) -> None:
        self._sii = sii
        self._sessions = sessions

    async def profile(self, auth: AuthenticatedSession) -> StudentProfile:
        return await guarded(self._sessions, auth, self._sii.get_profile(auth.token))

    async def grades(self, auth: AuthenticatedSession) -> list[GradesPeriodView]:
        periods = await guarded(self._sessions, auth, self._sii.get_grades(auth.token))
        return build_grades_view(periods)

    async def kardex(self, auth: AuthenticatedSession) -> KardexView:
        kardex = await guarded(self._sessions, auth, self._sii.get_kardex(auth.token))
        return build_kardex_view(kardex.progress_pct, kardex.entries)

    async def schedule(self, auth: AuthenticatedSession) -> list[SchedulePeriodView]:
        periods = await guarded(self._sessions, auth, self._sii.get_schedule(auth.token))
        return [
            SchedulePeriodView(
                term_code=p.term_code,
                term_label=_term_label(p.term_code),
                year=p.year,
                description=p.description,
                courses=p.courses,
            )
            for p in periods
        ]
