"""Scenario parameters: what the student wants to try."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Outcome = Literal["pass", "fail"]
ServicioSocialStatus = Literal["not_started", "in_progress", "done"]


@dataclass
class ScenarioParams:
    max_credits_per_term: int | None = None  # None → curriculum rule
    include_summer: bool = False
    outcomes: dict[str, Outcome] = field(default_factory=dict)  # in-progress subjects
    grades: dict[str, float] = field(default_factory=dict)  # hypothetical finals
    postpone: dict[str, str] = field(default_factory=dict)  # clave → earliest term code
    servicio_social: ServicioSocialStatus = "not_started"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ScenarioParams:
        data = data or {}
        return cls(
            max_credits_per_term=data.get("max_credits_per_term"),
            include_summer=bool(data.get("include_summer", False)),
            outcomes=dict(data.get("outcomes") or {}),
            grades={k: float(v) for k, v in (data.get("grades") or {}).items()},
            postpone=dict(data.get("postpone") or {}),
            servicio_social=data.get("servicio_social") or "not_started",
        )
