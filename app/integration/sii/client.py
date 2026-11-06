"""HTTP adapter for the SII ITC API. Implements the `SiiGateway` port."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.application.models import GradesPeriod, Kardex, SchedulePeriod, StudentProfile
from app.core.errors import (
    InvalidCredentialsError,
    SiiBadResponseError,
    SiiUnauthorizedError,
    SiiUnavailableError,
)
from app.integration.sii import mappers
from app.integration.sii.raw_schemas import (
    RawGradesPeriod,
    RawKardex,
    RawProfile,
    RawSchedulePeriod,
)

logger = logging.getLogger(__name__)

PROFILE_PATH = "movil/estudiante"
KARDEX_PATH = "movil/estudiante/kardex"
GRADES_PATH = "movil/estudiante/calificaciones"
SCHEDULE_PATH = "movil/estudiante/horarios"
LOGIN_PATH = "login"


def build_http_client(base_url: str, timeout_seconds: float) -> httpx.AsyncClient:
    # Trailing slash so relative paths are appended to `/api` instead of replacing it.
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/") + "/",
        timeout=httpx.Timeout(timeout_seconds),
        headers={"Accept": "application/json", "User-Agent": "Trayecta/1.0"},
    )


class SiiClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    # ------------------------------------------------------------------ auth

    async def login(self, email: str, password: str) -> str:
        try:
            response = await self._http.post(LOGIN_PATH, json={"email": email, "password": password})
        except httpx.HTTPError as exc:
            logger.warning("SII login unreachable: %s", type(exc).__name__)
            raise SiiUnavailableError() from exc

        if response.status_code >= 500:
            raise SiiUnavailableError()
        payload = self._json(response, allow_errors=True)
        token = _extract_token(payload)
        if response.status_code >= 400 or not token:
            raise InvalidCredentialsError()
        return token

    # ------------------------------------------------------------------ data

    async def get_profile(self, token: str) -> StudentProfile:
        data = await self._get(PROFILE_PATH, token)
        return mappers.to_profile(self._parse(RawProfile, data))

    async def get_kardex(self, token: str) -> Kardex:
        data = await self._get(KARDEX_PATH, token)
        return mappers.to_kardex(self._parse(RawKardex, data))

    async def get_grades(self, token: str) -> list[GradesPeriod]:
        data = await self._get(GRADES_PATH, token)
        periods = [self._parse(RawGradesPeriod, item) for item in _as_list(data)]
        return mappers.to_grades(periods)

    async def get_schedule(self, token: str) -> list[SchedulePeriod]:
        data = await self._get(SCHEDULE_PATH, token)
        periods = [self._parse(RawSchedulePeriod, item) for item in _as_list(data)]
        return mappers.to_schedule(periods)

    # ------------------------------------------------------------------ helpers

    async def _get(self, path: str, token: str) -> Any:
        headers = {"Authorization": f"Bearer {token}"}
        response: httpx.Response | None = None
        for attempt in (1, 2):
            try:
                response = await self._http.get(path, headers=headers)
                break
            except httpx.ConnectError as exc:
                if attempt == 2:
                    raise SiiUnavailableError() from exc
            except httpx.HTTPError as exc:
                raise SiiUnavailableError() from exc
        assert response is not None

        if response.status_code in (401, 403):
            raise SiiUnauthorizedError()
        if response.status_code >= 500:
            raise SiiUnavailableError()
        if response.status_code >= 400:
            raise SiiBadResponseError()

        payload = self._json(response)
        if not isinstance(payload, dict):
            raise SiiBadResponseError()
        if payload.get("flag") is False:
            message = str(payload.get("message", "")).lower()
            if "token" in message or "autoriz" in message or "sesi" in message:
                raise SiiUnauthorizedError()
            raise SiiBadResponseError()
        return payload.get("data")

    @staticmethod
    def _json(response: httpx.Response, *, allow_errors: bool = False) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            if allow_errors:
                return None
            raise SiiBadResponseError() from exc

    @staticmethod
    def _parse(model: type, data: Any) -> Any:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            logger.warning("Unexpected SII payload for %s: %s", model.__name__, exc.error_count())
            raise SiiBadResponseError() from exc


def _extract_token(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("flag", "")).lower() not in {"success", "true"}:
        return None
    message = payload.get("message")
    if isinstance(message, dict):
        login = message.get("login")
        if isinstance(login, dict):
            token = login.get("token")
            if isinstance(token, str) and token.strip():
                return token.strip()
    return None


def _as_list(data: Any) -> list[Any]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise SiiBadResponseError()
