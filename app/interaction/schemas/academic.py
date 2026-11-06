from datetime import datetime

from pydantic import Field, field_validator

from app.interaction.schemas.common import ApiModel

# --------------------------------------------------------------------------- auth


class LoginRequest(ApiModel):
    email: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El correo es obligatorio.")
        return value


class LoginStudent(ApiModel):
    numero_control: str
    full_name: str
    email: str
    is_admin: bool = False


class LoginResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    student: LoginStudent


# --------------------------------------------------------------------------- profile


class StudentProfileResponse(ApiModel):
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


# --------------------------------------------------------------------------- grades


class PartialGradeDto(ApiModel):
    number: int
    grade: float | None


class CourseGradesDto(ApiModel):
    group_id: int
    clave: str
    name: str
    group_letter: str
    partials: list[PartialGradeDto]
    graded_count: int
    average: float | None
    final: float | None
    level: str


class GradesPeriodDto(ApiModel):
    term_code: str
    term_label: str
    year: int
    description: str
    average: float | None
    courses: list[CourseGradesDto]


class GradesResponse(ApiModel):
    periods: list[GradesPeriodDto]


# --------------------------------------------------------------------------- kardex


class KardexEntryDto(ApiModel):
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


class KardexSemesterDto(ApiModel):
    semester: int
    credits: int
    average: float | None
    entries: list[KardexEntryDto]


class KardexResponse(ApiModel):
    progress_pct: float
    accredited_credits: int
    average: float | None
    approved_count: int
    failed_count: int
    semesters: list[KardexSemesterDto]


# --------------------------------------------------------------------------- schedule


class ClassSessionDto(ApiModel):
    day: str
    start: str
    end: str
    room: str | None


class ScheduledCourseDto(ApiModel):
    group_id: int
    clave: str
    name: str
    group_letter: str
    plan_name: str | None
    sessions: list[ClassSessionDto]


class SchedulePeriodDto(ApiModel):
    term_code: str
    term_label: str
    year: int
    description: str
    courses: list[ScheduledCourseDto]


class ScheduleResponse(ApiModel):
    periods: list[SchedulePeriodDto]
