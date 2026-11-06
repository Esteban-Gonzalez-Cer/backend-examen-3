"""Administration backend of the What-If Simulator (restricted to ADMIN_CONTROL_NUMBERS)."""

from fastapi import APIRouter, Depends, Response, status

from app.application.services.admin_service import AdminCurriculumService
from app.interaction.dependencies import get_admin_service, require_admin
from app.interaction.schemas.admin import (
    RequisiteRequest,
    RequisiteResponse,
    RulesBody,
    SubjectBody,
    SubjectCreateRequest,
    SubjectResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/subjects", response_model=list[SubjectResponse], summary="Materias de la retícula")
async def list_subjects(service: AdminCurriculumService = Depends(get_admin_service)) -> list[SubjectResponse]:
    return [SubjectResponse.model_validate(s) for s in await service.list_subjects()]


@router.post(
    "/subjects", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED, summary="Crear materia"
)
async def create_subject(
    body: SubjectCreateRequest, service: AdminCurriculumService = Depends(get_admin_service)
) -> SubjectResponse:
    data = body.model_dump(exclude={"clave"})
    subject = SubjectBody(**data).to_domain(body.clave)
    return SubjectResponse.model_validate(await service.create_subject(subject))


@router.put("/subjects/{clave}", response_model=SubjectResponse, summary="Actualizar materia")
async def update_subject(
    clave: str, body: SubjectBody, service: AdminCurriculumService = Depends(get_admin_service)
) -> SubjectResponse:
    return SubjectResponse.model_validate(await service.update_subject(clave, body.to_domain(clave)))


@router.delete("/subjects/{clave}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar materia")
async def delete_subject(clave: str, service: AdminCurriculumService = Depends(get_admin_service)) -> Response:
    await service.delete_subject(clave)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/requisites", response_model=list[RequisiteResponse], summary="Requisitos (aristas del DAG)")
async def list_requisites(
    service: AdminCurriculumService = Depends(get_admin_service),
) -> list[RequisiteResponse]:
    return [RequisiteResponse.model_validate(r) for r in await service.list_requisites()]


@router.post(
    "/requisites",
    response_model=RequisiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar requisito (rechaza ciclos)",
)
async def add_requisite(
    body: RequisiteRequest, service: AdminCurriculumService = Depends(get_admin_service)
) -> RequisiteResponse:
    return RequisiteResponse.model_validate(await service.add_requisite(body.to_domain()))


@router.delete(
    "/requisites/{requisite_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar requisito"
)
async def delete_requisite(
    requisite_id: int, service: AdminCurriculumService = Depends(get_admin_service)
) -> Response:
    await service.delete_requisite(requisite_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/rules", response_model=RulesBody, summary="Reglas de carga académica")
async def get_rules(service: AdminCurriculumService = Depends(get_admin_service)) -> RulesBody:
    return RulesBody.model_validate(await service.get_rules())


@router.put("/rules", response_model=RulesBody, summary="Actualizar reglas de carga académica")
async def update_rules(body: RulesBody, service: AdminCurriculumService = Depends(get_admin_service)) -> RulesBody:
    return RulesBody.model_validate(await service.update_rules(body.to_domain()))
