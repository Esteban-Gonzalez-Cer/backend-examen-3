"""Proxied SII endpoints. The frontend never talks to SII directly."""

from fastapi import APIRouter, Depends

from app.application.models import AuthenticatedSession
from app.application.services.academic_service import AcademicService
from app.interaction.dependencies import get_academic_service, get_current_session
from app.interaction.schemas.academic import (
    GradesResponse,
    KardexResponse,
    ScheduleResponse,
    StudentProfileResponse,
)

router = APIRouter(prefix="/students/me", tags=["student"])


@router.get("", response_model=StudentProfileResponse, summary="Perfil del estudiante")
async def profile(
    current: AuthenticatedSession = Depends(get_current_session),
    service: AcademicService = Depends(get_academic_service),
) -> StudentProfileResponse:
    return StudentProfileResponse.model_validate(await service.profile(current))


@router.get("/grades", response_model=GradesResponse, summary="Calificaciones del periodo actual")
async def grades(
    current: AuthenticatedSession = Depends(get_current_session),
    service: AcademicService = Depends(get_academic_service),
) -> GradesResponse:
    return GradesResponse.model_validate({"periods": await service.grades(current)})


@router.get("/kardex", response_model=KardexResponse, summary="Historial académico completo")
async def kardex(
    current: AuthenticatedSession = Depends(get_current_session),
    service: AcademicService = Depends(get_academic_service),
) -> KardexResponse:
    return KardexResponse.model_validate(await service.kardex(current))


@router.get("/schedule", response_model=ScheduleResponse, summary="Horario del semestre actual")
async def schedule(
    current: AuthenticatedSession = Depends(get_current_session),
    service: AcademicService = Depends(get_academic_service),
) -> ScheduleResponse:
    return ScheduleResponse.model_validate({"periods": await service.schedule(current)})
