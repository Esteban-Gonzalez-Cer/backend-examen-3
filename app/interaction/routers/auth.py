"""Login, session restore (refresh) and logout.

The SII token (access token) goes in the JSON body and the frontend keeps it in memory only.
The refresh token goes in an HttpOnly cookie that JavaScript cannot read, scoped to /api/v1/auth.
"""

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials

from app.application.services.auth_service import AuthService, SessionGrant
from app.core.config import Settings
from app.core.errors import AppError
from app.interaction.dependencies import bearer_scheme, get_auth_service, settings_dep
from app.interaction.error_handlers import error_response
from app.interaction.schemas.academic import LoginRequest, LoginResponse, LoginStudent

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "trayecta_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def cookie_is_secure(request: Request, settings: Settings) -> bool:
    """HTTPS-only everywhere except local development (Safari ignores Secure cookies on http)."""
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return (request.url.hostname or "") not in LOCAL_HOSTS


def _set_refresh_cookie(response: Response, value: str, max_age: int, secure: bool) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        value,
        max_age=max_age,  # the browser drops it when the session would expire anyway
        path=REFRESH_COOKIE_PATH,  # only sent to login/refresh/logout, never to data endpoints
        httponly=True,  # invisible to JavaScript → an XSS cannot steal it
        secure=secure,  # HTTPS only (except on localhost)
        samesite="strict",  # never sent on requests started by another site (CSRF)
    )


def _clear_refresh_cookie(response: Response, secure: bool) -> None:
    # Same name, path and flags as when it was set, otherwise the browser keeps the old one.
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="strict",
    )


def _grant_response(
    grant: SessionGrant, request: Request, response: Response, auth: AuthService, settings: Settings
) -> LoginResponse:
    _set_refresh_cookie(
        response,
        grant.refresh_token,
        auth.remaining_seconds(grant.expires_at),
        cookie_is_secure(request, settings),
    )
    return LoginResponse(
        access_token=grant.access_token,
        expires_at=grant.expires_at,
        student=LoginStudent(
            numero_control=grant.numero_control,
            full_name=grant.full_name,
            email=grant.email,
            is_admin=grant.numero_control in settings.admin_control_numbers,
        ),
    )


@router.post("/login", response_model=LoginResponse, summary="Iniciar sesión con las credenciales del SII")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(settings_dep),
) -> LoginResponse:
    grant = await auth.login(body.email, body.password)
    return _grant_response(grant, request, response, auth, settings)


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Restaurar la sesión tras recargar la página (usa la cookie HttpOnly)",
)
async def refresh(
    request: Request,
    response: Response,
    trayecta_refresh: str | None = Cookie(default=None),
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(settings_dep),
) -> LoginResponse | Response:
    try:
        grant = await auth.refresh(trayecta_refresh)
    except AppError as exc:
        # A dead cookie is useless: report the error as usual and tell the browser to drop it.
        error = error_response(exc)
        _clear_refresh_cookie(error, cookie_is_secure(request, settings))
        return error
    return _grant_response(grant, request, response, auth, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar sesión y revocarla en el servidor")
async def logout(
    request: Request,
    trayecta_refresh: str | None = Cookie(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(settings_dep),
) -> Response:
    await auth.logout(trayecta_refresh, credentials.credentials if credentials else None)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, cookie_is_secure(request, settings))
    return response

