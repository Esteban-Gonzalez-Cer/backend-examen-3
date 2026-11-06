"""What-If Simulator use cases: baseline analysis, live simulation and saved scenarios."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.models import AuthenticatedSession, Scenario, Term
from app.application.ports import (
    CurriculumRepository,
    ScenarioRepository,
    SessionRepository,
    SiiGateway,
)
from app.application.services.sii_guard import guarded
from app.application.whatif.engine.graph import CurriculumGraph
from app.application.whatif.engine.params import ScenarioParams
from app.application.whatif.engine.results import SimulationResult
from app.application.whatif.engine.simulator import graduation_delay, simulate
from app.application.whatif.engine.state import StudentState, build_student_state
from app.core.errors import CurriculumNotConfiguredError, NotFoundError, ValidationFailedError


def _utcnow() -> datetime:
    return datetime.now(UTC)


def validate_params(graph: CurriculumGraph, params: ScenarioParams) -> None:
    unknown = [
        c for c in (*params.outcomes, *params.grades, *params.postpone) if c not in graph.subjects
    ]
    if unknown:
        raise ValidationFailedError(
            "Hay materias desconocidas en el escenario.", details={"claves": sorted(set(unknown))}
        )
    for clave, code in params.postpone.items():
        try:
            Term.parse(code)
        except ValueError as exc:
            raise ValidationFailedError(f"Periodo inválido para {clave}: {code}.") from exc


class WhatIfService:
    def __init__(
        self,
        sii: SiiGateway,
        sessions: SessionRepository,
        curricula: CurriculumRepository,
    ) -> None:
        self._sii = sii
        self._sessions = sessions
        self._curricula = curricula

    async def _load(self, auth: AuthenticatedSession) -> tuple[CurriculumGraph, StudentState]:
        curriculum = await self._curricula.get_active()
        if curriculum is None or not curriculum.subjects:
            raise CurriculumNotConfiguredError()
        kardex, periods = await guarded(
            self._sessions,
            auth,
            asyncio.gather(self._sii.get_kardex(auth.token), self._sii.get_grades(auth.token)),
        )
        graph = CurriculumGraph.from_curriculum(curriculum)
        return graph, build_student_state(graph, kardex, periods)

    @staticmethod
    def _run(graph: CurriculumGraph, state: StudentState, params: ScenarioParams) -> SimulationResult:
        validate_params(graph, params)
        result = simulate(graph, state, params)
        baseline = simulate(graph, state, ScenarioParams(), with_sensitivity=False)
        result.delta_vs_baseline = graduation_delay(
            Term.parse(baseline.projected_graduation_term) if baseline.projected_graduation_term else None,
            Term.parse(result.projected_graduation_term) if result.projected_graduation_term else None,
        )
        return result

    async def analysis(self, auth: AuthenticatedSession) -> SimulationResult:
        graph, state = await self._load(auth)
        return self._run(graph, state, ScenarioParams())

    async def simulate(self, auth: AuthenticatedSession, params: ScenarioParams) -> SimulationResult:
        graph, state = await self._load(auth)
        return self._run(graph, state, params)


def summarize(result: SimulationResult) -> dict:
    return {
        "projected_graduation_term": result.projected_graduation_term,
        "projected_graduation_label": result.projected_graduation_label,
        "terms_remaining": result.terms_remaining,
        "delta_vs_baseline": result.delta_vs_baseline,
        "projected_gpa": result.gpa.projected,
        "computed_at": _utcnow().isoformat(),
    }


class ScenarioService:
    def __init__(
        self,
        whatif: WhatIfService,
        scenarios: ScenarioRepository,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._whatif = whatif
        self._scenarios = scenarios
        self._clock = clock

    async def list(self, auth: AuthenticatedSession) -> list[Scenario]:
        return await self._scenarios.list_for_student(auth.numero_control)

    async def create(self, auth: AuthenticatedSession, name: str, params: ScenarioParams) -> Scenario:
        result = await self._whatif.simulate(auth, params)
        now = self._clock()
        return await self._scenarios.create(
            Scenario(
                id=uuid4(),
                numero_control=auth.numero_control,
                name=name.strip(),
                params=params.to_dict(),
                result_summary=summarize(result),
                created_at=now,
                updated_at=now,
            )
        )

    async def _get(self, auth: AuthenticatedSession, scenario_id: UUID) -> Scenario:
        scenario = await self._scenarios.get(scenario_id, auth.numero_control)
        if scenario is None:
            raise NotFoundError("El escenario no existe.")
        return scenario

    async def detail(self, auth: AuthenticatedSession, scenario_id: UUID) -> tuple[Scenario, SimulationResult]:
        scenario = await self._get(auth, scenario_id)
        result = await self._whatif.simulate(auth, ScenarioParams.from_dict(scenario.params))
        return scenario, result

    async def update(
        self,
        auth: AuthenticatedSession,
        scenario_id: UUID,
        name: str | None,
        params: ScenarioParams | None,
    ) -> Scenario:
        scenario = await self._get(auth, scenario_id)
        if name is not None:
            scenario.name = name.strip()
        if params is not None:
            result = await self._whatif.simulate(auth, params)
            scenario.params = params.to_dict()
            scenario.result_summary = summarize(result)
        scenario.updated_at = self._clock()
        return await self._scenarios.update(scenario)

    async def delete(self, auth: AuthenticatedSession, scenario_id: UUID) -> None:
        if not await self._scenarios.delete(scenario_id, auth.numero_control):
            raise NotFoundError("El escenario no existe.")
