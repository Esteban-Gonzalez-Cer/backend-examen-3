from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.application.models import AuthenticatedSession, Scenario
from app.application.services.whatif_service import ScenarioService, WhatIfService
from app.interaction.dependencies import (
    get_current_session,
    get_scenario_service,
    get_whatif_service,
)
from app.interaction.schemas.whatif import (
    ScenarioCreateRequest,
    ScenarioDetailResponse,
    ScenarioParamsDto,
    ScenarioResponse,
    ScenarioSummaryDto,
    ScenarioUpdateRequest,
    SimulationResponse,
)

router = APIRouter(prefix="/whatif", tags=["what-if"])


def _scenario_dto(scenario: Scenario) -> ScenarioResponse:
    return ScenarioResponse(
        id=scenario.id,
        name=scenario.name,
        params=ScenarioParamsDto.from_stored(scenario.params),
        summary=ScenarioSummaryDto.model_validate(scenario.result_summary),
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


@router.get("/analysis", response_model=SimulationResponse, summary="Análisis base de tu trayectoria")
async def analysis(
    current: AuthenticatedSession = Depends(get_current_session),
    service: WhatIfService = Depends(get_whatif_service),
) -> SimulationResponse:
    return SimulationResponse.model_validate(await service.analysis(current))


@router.post("/simulate", response_model=SimulationResponse, summary="Simular un escenario sin guardarlo")
async def simulate(
    body: ScenarioParamsDto,
    current: AuthenticatedSession = Depends(get_current_session),
    service: WhatIfService = Depends(get_whatif_service),
) -> SimulationResponse:
    return SimulationResponse.model_validate(await service.simulate(current, body.to_domain()))


@router.get("/scenarios", response_model=list[ScenarioResponse], summary="Escenarios guardados")
async def list_scenarios(
    current: AuthenticatedSession = Depends(get_current_session),
    service: ScenarioService = Depends(get_scenario_service),
) -> list[ScenarioResponse]:
    return [_scenario_dto(s) for s in await service.list(current)]


@router.post(
    "/scenarios",
    response_model=ScenarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar un escenario",
)
async def create_scenario(
    body: ScenarioCreateRequest,
    current: AuthenticatedSession = Depends(get_current_session),
    service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioResponse:
    return _scenario_dto(await service.create(current, body.name, body.params.to_domain()))


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioDetailResponse,
    summary="Escenario guardado recalculado con tu kardex actual",
)
async def get_scenario(
    scenario_id: UUID,
    current: AuthenticatedSession = Depends(get_current_session),
    service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioDetailResponse:
    scenario, result = await service.detail(current, scenario_id)
    return ScenarioDetailResponse(
        scenario=_scenario_dto(scenario), result=SimulationResponse.model_validate(result)
    )


@router.put("/scenarios/{scenario_id}", response_model=ScenarioResponse, summary="Actualizar escenario")
async def update_scenario(
    scenario_id: UUID,
    body: ScenarioUpdateRequest,
    current: AuthenticatedSession = Depends(get_current_session),
    service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioResponse:
    params = body.params.to_domain() if body.params else None
    return _scenario_dto(await service.update(current, scenario_id, body.name, params))


@router.delete(
    "/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar escenario",
)
async def delete_scenario(
    scenario_id: UUID,
    current: AuthenticatedSession = Depends(get_current_session),
    service: ScenarioService = Depends(get_scenario_service),
) -> Response:
    await service.delete(current, scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
