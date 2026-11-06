"""Output structures of the What-If engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlannedSubject:
    clave: str
    name: str
    credits: int
    is_retake: bool
    counts_toward_load: bool


@dataclass
class PlannedTerm:
    term: str
    label: str
    is_summer: bool
    load_credits: int
    credits_after: int
    subjects: list[PlannedSubject] = field(default_factory=list)


@dataclass
class CriticalStep:
    clave: str
    name: str
    term: str
    term_label: str
    reason: str  # start | retake | prereq | credit_gate | postponed | load_limit | summer_rules
    detail: str


@dataclass
class Bottleneck:
    clave: str
    name: str
    kind: str  # hidden | structural | gate
    score: float
    descendants: int
    downstream_credits: int
    slack: int | None
    delay_terms: int | None
    detail: str


@dataclass
class FailureImpact:
    clave: str
    name: str
    scenario: str  # fail | postpone
    delay_terms: int | None
    new_graduation_term: str | None
    new_graduation_label: str | None


@dataclass
class GateMilestone:
    pct: float
    credits_needed: int
    subjects: list[str]
    reached_now: bool
    projected_term: str | None
    projected_label: str | None


@dataclass
class CreditSummary:
    approved: int
    in_progress: int
    after_current_term: int
    total: int
    approved_pct: float
    after_current_pct: float


@dataclass
class GpaProjection:
    current: float | None
    projected: float | None


@dataclass
class NodeView:
    clave: str
    name: str
    credits: int
    suggested_semester: int
    grid_row: int
    grid_col: int
    kind: str
    status: str  # approved | in_progress | failed_sim | available | planned | unreachable
    grade_label: str | None
    planned_term: str | None
    planned_label: str | None
    min_credit_pct: float | None
    on_critical_path: bool
    slack: int | None


@dataclass
class EdgeView:
    source: str
    target: str
    type: str
    critical: bool


@dataclass
class RulesView:
    max_credits_per_term: int
    min_credits_per_term: int
    summer_max_subjects: int
    passing_grade: int


@dataclass
class SimulationResult:
    current_term: str
    current_term_label: str
    projected_graduation_term: str | None
    projected_graduation_label: str | None
    terms_remaining: int | None
    delta_vs_baseline: int | None
    credits: CreditSummary
    plan: list[PlannedTerm]
    critical_path: list[CriticalStep]
    bottlenecks: list[Bottleneck]
    failure_impact: list[FailureImpact]
    gates: list[GateMilestone]
    gpa: GpaProjection
    nodes: list[NodeView]
    edges: list[EdgeView]
    warnings: list[str]
    unreachable: list[str]
    rules: RulesView | None = None
