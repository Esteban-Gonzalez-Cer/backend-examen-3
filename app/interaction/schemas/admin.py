from typing import Literal

from pydantic import Field

from app.application.models import CurriculumRules, Requisite, Subject
from app.interaction.schemas.common import ApiModel

SubjectKindDto = Literal["generic", "specialty", "special_requirement"]


class SubjectBody(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    credits: int = Field(ge=0, le=20)
    ht: int = Field(default=0, ge=0, le=20)
    hp: int = Field(default=0, ge=0, le=20)
    suggested_semester: int = Field(ge=1, le=12)
    grid_row: int = Field(ge=1, le=12)
    grid_col: int = Field(ge=1, le=12)
    kind: SubjectKindDto = "generic"
    min_credit_pct: float | None = Field(default=None, ge=0, le=100)
    counts_toward_load: bool = True

    def to_domain(self, clave: str) -> Subject:
        return Subject(clave=clave, **self.model_dump())


class SubjectCreateRequest(SubjectBody):
    clave: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9-]+$")


class SubjectResponse(ApiModel):
    id: int | None
    clave: str
    name: str
    credits: int
    ht: int
    hp: int
    suggested_semester: int
    grid_row: int
    grid_col: int
    kind: str
    min_credit_pct: float | None
    counts_toward_load: bool


class RequisiteRequest(ApiModel):
    subject_clave: str = Field(min_length=3, max_length=20)
    requires_clave: str = Field(min_length=3, max_length=20)
    type: Literal["prereq", "coreq"] = "prereq"

    def to_domain(self) -> Requisite:
        return Requisite(
            subject_clave=self.subject_clave, requires_clave=self.requires_clave, type=self.type
        )


class RequisiteResponse(ApiModel):
    id: int | None
    subject_clave: str
    requires_clave: str
    type: str


class RulesBody(ApiModel):
    max_credits_per_term: int = Field(ge=4, le=60)
    min_credits_per_term: int = Field(ge=0, le=60)
    summer_max_subjects: int = Field(ge=0, le=6)
    passing_grade: int = Field(ge=50, le=100)

    def to_domain(self) -> CurriculumRules:
        return CurriculumRules(**self.model_dump())
