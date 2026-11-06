from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.application.whatif.engine.params import ScenarioParams
from app.interaction.schemas.common import ApiModel

# --------------------------------------------------------------------------- request


class ScenarioParamsDto(ApiModel):
    max_credits_per_term: int | None = Field(default=None, ge=4, le=60)
    include_summer: bool = False
    outcomes: dict[str, Literal["pass", "fail"]] = {}
    grades: dict[str, float] = {}
    postpone: dict[str, str] = {}
    servicio_social: Literal["not_started", "in_progress", "done"] = "not_started"

    @field_validator("grades")
    @classmethod
    def _grades_in_range(cls, value: dict[str, float]) -> dict[str, float]:
        for clave, grade in value.items():
            if not 0 <= grade <= 100:
                raise ValueError(f"Calificación fuera de rango para {clave}.")
        return value

    def to_domain(self) -> ScenarioParams:
        return ScenarioParams(
            max_credits_per_term=self.max_credits_per_term,
            include_summer=self.include_summer,
            outcomes=dict(self.outcomes),
            grades=dict(self.grades),
            postpone=dict(self.postpone),
            servicio_social=self.servicio_social,
        )

    @classmethod
    def from_stored(cls, data: dict[str, Any]) -> "ScenarioParamsDto":
        params = ScenarioParams.from_dict(data)
        return cls(
            max_credits_per_term=params.max_credits_per_term,
            include_summer=params.include_summer,
            outcomes=params.outcomes,
            grades=params.grades,
            postpone=params.postpone,
            servicio_social=params.servicio_social,
        )


class ScenarioCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    params: ScenarioParamsDto


class ScenarioUpdateRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    params: ScenarioParamsDto | None = None


# --------------------------------------------------------------------------- simulation result


class PlannedSubjectDto(ApiModel):
    clave: str
    name: str
    credits: int
    is_retake: bool
    counts_toward_load: bool


class PlannedTermDto(ApiModel):
    term: str
    label: str
    is_summer: bool
    load_credits: int
    credits_after: int
    subjects: list[PlannedSubjectDto]


class CriticalStepDto(ApiModel):
    clave: str
    name: str
    term: str
    term_label: str
    reason: str
    detail: str


class BottleneckDto(ApiModel):
    clave: str
    name: str
    kind: str
    score: float
    descendants: int
    downstream_credits: int
    slack: int | None
    delay_terms: int | None
    detail: str


class FailureImpactDto(ApiModel):
    clave: str
    name: str
    scenario: str
    delay_terms: int | None
    new_graduation_term: str | None
    new_graduation_label: str | None


class GateMilestoneDto(ApiModel):
    pct: float
    credits_needed: int
    subjects: list[str]
    reached_now: bool
    projected_term: str | None
    projected_label: str | None


class CreditSummaryDto(ApiModel):
    approved: int
    in_progress: int
    after_current_term: int
    total: int
    approved_pct: float
    after_current_pct: float


class GpaProjectionDto(ApiModel):
    current: float | None
    projected: float | None


class NodeDto(ApiModel):
    clave: str
    name: str
    credits: int
    suggested_semester: int
    grid_row: int
    grid_col: int
    kind: str
    status: str
    grade_label: str | None
    planned_term: str | None
    planned_label: str | None
    min_credit_pct: float | None
    on_critical_path: bool
    slack: int | None


class EdgeDto(ApiModel):
    source: str
    target: str
    type: str
    critical: bool


class RulesDto(ApiModel):
    max_credits_per_term: int
    min_credits_per_term: int
    summer_max_subjects: int
    passing_grade: int


class SimulationResponse(ApiModel):
    current_term: str
    current_term_label: str
    projected_graduation_term: str | None
    projected_graduation_label: str | None
    terms_remaining: int | None
    delta_vs_baseline: int | None
    credits: CreditSummaryDto
    plan: list[PlannedTermDto]
    critical_path: list[CriticalStepDto]
    bottlenecks: list[BottleneckDto]
    failure_impact: list[FailureImpactDto]
    gates: list[GateMilestoneDto]
    gpa: GpaProjectionDto
    nodes: list[NodeDto]
    edges: list[EdgeDto]
    warnings: list[str]
    unreachable: list[str]
    rules: RulesDto | None = None


# --------------------------------------------------------------------------- scenarios


class ScenarioSummaryDto(ApiModel):
    projected_graduation_term: str | None = None
    projected_graduation_label: str | None = None
    terms_remaining: int | None = None
    delta_vs_baseline: int | None = None
    projected_gpa: float | None = None
    computed_at: str | None = None


class ScenarioResponse(ApiModel):
    id: UUID
    name: str
    params: ScenarioParamsDto
    summary: ScenarioSummaryDto
    created_at: datetime
    updated_at: datetime


class ScenarioDetailResponse(ApiModel):
    scenario: ScenarioResponse
    result: SimulationResponse
