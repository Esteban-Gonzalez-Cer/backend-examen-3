"""FastAPI dependency wiring: adapters → services, bearer token → current session."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.models import AuthenticatedSession
from app.application.ports import SiiGateway
from app.application.services.academic_service import AcademicService
from app.application.services.admin_service import AdminCurriculumService
from app.application.services.auth_service import AuthService
from app.application.services.whatif_service import ScenarioService, WhatIfService
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError
from app.data.repositories.curriculum_repo import SqlCurriculumRepository
from app.data.repositories.scenario_repo import SqlScenarioRepository
from app.data.repositories.session_repo import SqlSessionRepository, SqlStudentRepository
from app.integration.sii.client import SiiClient

bearer_scheme = HTTPBearer(auto_error=False, description="Token devuelto por POST /auth/login")


def settings_dep() -> Settings:
    return get_settings()


# --------------------------------------------------------------------------- adapters


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_sii_gateway(http: httpx.AsyncClient = Depends(get_http_client)) -> SiiGateway:
    return SiiClient(http)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_session_repo(db: AsyncSession = Depends(get_db)) -> SqlSessionRepository:
    return SqlSessionRepository(db)


def get_student_repo(db: AsyncSession = Depends(get_db)) -> SqlStudentRepository:
    return SqlStudentRepository(db)


def get_curriculum_repo(db: AsyncSession = Depends(get_db)) -> SqlCurriculumRepository:
    return SqlCurriculumRepository(db)


def get_scenario_repo(db: AsyncSession = Depends(get_db)) -> SqlScenarioRepository:
    return SqlScenarioRepository(db)


# --------------------------------------------------------------------------- services


def get_auth_service(
    sii: SiiGateway = Depends(get_sii_gateway),
    sessions: SqlSessionRepository = Depends(get_session_repo),
    students: SqlStudentRepository = Depends(get_student_repo),
    curricula: SqlCurriculumRepository = Depends(get_curriculum_repo),
    settings: Settings = Depends(settings_dep),
) -> AuthService:
    return AuthService(sii, sessions, students, curricula, settings.session_ttl_minutes)


def get_academic_service(
    sii: SiiGateway = Depends(get_sii_gateway),
    sessions: SqlSessionRepository = Depends(get_session_repo),
) -> AcademicService:
    return AcademicService(sii, sessions)


def get_whatif_service(
    sii: SiiGateway = Depends(get_sii_gateway),
    sessions: SqlSessionRepository = Depends(get_session_repo),
    curricula: SqlCurriculumRepository = Depends(get_curriculum_repo),
) -> WhatIfService:
    return WhatIfService(sii, sessions, curricula)


def get_scenario_service(
    whatif: WhatIfService = Depends(get_whatif_service),
    scenarios: SqlScenarioRepository = Depends(get_scenario_repo),
) -> ScenarioService:
    return ScenarioService(whatif, scenarios)


def get_admin_service(
    curricula: SqlCurriculumRepository = Depends(get_curriculum_repo),
) -> AdminCurriculumService:
    return AdminCurriculumService(curricula)


# --------------------------------------------------------------------------- auth guards


async def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
) -> AuthenticatedSession:
    token = credentials.credentials if credentials else None
    return await auth.authenticate(token)


async def require_admin(
    current: AuthenticatedSession = Depends(get_current_session),
    settings: Settings = Depends(settings_dep),
) -> AuthenticatedSession:
    if current.numero_control not in settings.admin_control_numbers:
        raise ForbiddenError()
    return current
