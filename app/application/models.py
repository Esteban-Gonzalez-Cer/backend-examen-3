"""Domain models shared by the application layer and the adapters that implement its ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import total_ordering
from typing import Any, Literal
from uuid import UUID

PASSING_GRADE_DEFAULT = 70

# --------------------------------------------------------------------------- terms

TermKind = Literal["1", "V", "2"]
_KIND_ORDER: dict[str, int] = {"1": 0, "V": 1, "2": 2}
_KIND_LABEL: dict[str, str] = {"1": "Ene–Jun", "V": "Verano", "2": "Ago–Dic"}


@total_ordering
@dataclass(frozen=True)
class Term:
    """An academic period such as `26/2` (Ago–Dic 2026) or `25/V` (Verano 2025)."""

    year: int
    kind: TermKind

    @classmethod
    def parse(cls, code: str) -> Term:
        try:
            year_part, kind_part = code.strip().upper().split("/")
            year = int(year_part)
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"Periodo inválido: {code!r}") from exc
        if kind_part not in _KIND_ORDER:
            raise ValueError(f"Periodo inválido: {code!r}")
        if year < 100:
            year += 2000
        return cls(year=year, kind=kind_part)  # type: ignore[arg-type]

    @classmethod
    def from_date(cls, moment: datetime) -> Term:
        if moment.month <= 6:
            return cls(moment.year, "1")
        if moment.month == 7:
            return cls(moment.year, "V")
        return cls(moment.year, "2")

    @property
    def code(self) -> str:
        return f"{self.year % 100:02d}/{self.kind}"

    @property
    def label(self) -> str:
        return f"{_KIND_LABEL[self.kind]} {self.year}"

    @property
    def is_summer(self) -> bool:
        return self.kind == "V"

    @property
    def ordinal(self) -> int:
        return self.year * 3 + _KIND_ORDER[self.kind]

    @property
    def semester_index(self) -> int:
        """Regular-semester index; a summer counts together with the spring term before it."""
        return self.year * 2 + (1 if self.kind == "2" else 0)

    def next(self, include_summer: bool = False) -> Term:
        if self.kind == "1":
            return Term(self.year, "V") if include_summer else Term(self.year, "2")
        if self.kind == "V":
            return Term(self.year, "2")
        return Term(self.year + 1, "1")

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Term):
            return NotImplemented
        return self.ordinal < other.ordinal


# --------------------------------------------------------------------------- grades


def parse_grade(raw: object) -> tuple[float | None, str | None]:
    """SII sends grades as strings: "95", "AC" or null."""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    try:
        return float(text), text
    except ValueError:
        return None, text.upper()


def is_accredited(numeric: float | None, label: str | None, passing_grade: float) -> bool:
    if numeric is not None:
        return numeric >= passing_grade
    return label in {"AC", "ACA", "ACREDITADA", "ACREDITADO"}


def grade_level(value: float | None, passing_grade: float = PASSING_GRADE_DEFAULT) -> str:
    """Traffic-light level used by the UI: good (≥85), warning (passing–84), risk (<passing)."""
    if value is None:
        return "none"
    if value >= 85:
        return "good"
    if value >= passing_grade:
        return "warning"
    return "risk"


# --------------------------------------------------------------------------- SII data


@dataclass
class StudentProfile:
    numero_control: str
    full_name: str
    email: str
    semester: int
    credits_accumulated: int
    weighted_average: float
    arithmetic_average: float
    subjects_taken: int
    subjects_approved: int
    subjects_failed: int
    subjects_failed_not_accredited: int
    complementary_credits: int
    progress_pct: float
    progress_in_progress_pct: float | None
    photo_data_url: str | None


@dataclass
class KardexEntry:
    clave: str
    name: str
    term_code: str
    credits: int
    grade: float | None
    grade_label: str | None
    description: str
    semester: int


@dataclass
class Kardex:
    progress_pct: float
    entries: list[KardexEntry]


@dataclass
class PartialGrade:
    number: int
    grade: float | None


@dataclass
class CourseGrades:
    group_id: int
    clave: str
    name: str
    group_letter: str
    partials: list[PartialGrade]


@dataclass
class GradesPeriod:
    term_code: str
    year: int
    description: str
    courses: list[CourseGrades]


@dataclass
class ClassSession:
    day: str  # lunes … sabado
    start: str  # HH:MM
    end: str  # HH:MM
    room: str | None


@dataclass
class ScheduledCourse:
    group_id: int
    clave: str
    name: str
    group_letter: str
    plan_name: str | None
    sessions: list[ClassSession]


@dataclass
class SchedulePeriod:
    term_code: str
    year: int
    description: str
    courses: list[ScheduledCourse]


# --------------------------------------------------------------------------- curriculum

SubjectKind = Literal["generic", "specialty", "special_requirement"]
RequisiteType = Literal["prereq", "coreq"]


@dataclass
class Subject:
    clave: str
    name: str
    credits: int
    ht: int
    hp: int
    suggested_semester: int
    grid_row: int
    grid_col: int
    kind: SubjectKind = "generic"
    min_credit_pct: float | None = None
    counts_toward_load: bool = True
    id: int | None = None


@dataclass
class Requisite:
    subject_clave: str
    requires_clave: str
    type: RequisiteType
    id: int | None = None


@dataclass
class CurriculumRules:
    max_credits_per_term: int = 36
    min_credits_per_term: int = 20
    summer_max_subjects: int = 2
    passing_grade: int = PASSING_GRADE_DEFAULT


@dataclass
class Curriculum:
    id: int
    code: str
    specialty_code: str | None
    name: str
    total_credits: int
    subjects: list[Subject] = field(default_factory=list)
    requisites: list[Requisite] = field(default_factory=list)
    rules: CurriculumRules = field(default_factory=CurriculumRules)


# --------------------------------------------------------------------------- our own records


@dataclass
class AuthSession:
    token_hash: str
    numero_control: str
    issued_at: datetime
    expires_at: datetime
    # sha256 of the opaque refresh token kept in the HttpOnly cookie.
    refresh_hash: str | None = None
    # The SII token encrypted with the server secret, so a refresh can hand it back.
    token_encrypted: str | None = None


@dataclass
class AuthenticatedSession:
    """The caller of a protected endpoint, resolved from the bearer token."""

    token: str
    token_hash: str
    numero_control: str
    expires_at: datetime


@dataclass
class StudentRecord:
    numero_control: str
    full_name: str
    email: str
    curriculum_id: int | None
    last_login_at: datetime


@dataclass
class Scenario:
    id: UUID
    numero_control: str
    name: str
    params: dict[str, Any]
    result_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime
