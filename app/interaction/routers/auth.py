from fastapi import APIRouter, Depends

from app.application.services.auth_service import AuthService
from app.core.config import Settings
from app.interaction.dependencies import get_auth_service, settings_dep
from app.interaction.schemas.academic import LoginRequest, LoginResponse, LoginStudent

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse, summary="Iniciar sesión con las credenciales del SII")
async def login(
    body: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(settings_dep),
) -> LoginResponse:
    result = await auth.login(body.email, body.password)
    return LoginResponse(
        access_token=result.token,
        expires_at=result.expires_at,
        student=LoginStudent(
            numero_control=result.profile.numero_control,
            full_name=result.profile.full_name,
            email=result.profile.email,
            is_admin=result.profile.numero_control in settings.admin_control_numbers,
        ),
    )
