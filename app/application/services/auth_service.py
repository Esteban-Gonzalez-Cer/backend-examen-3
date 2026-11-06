"""Login against SII and keep a server-side registry of the issued tokens."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.models import (
    AuthenticatedSession,
    AuthSession,
    StudentProfile,
    StudentRecord,
)
from app.application.ports import (
    CurriculumRepository,
    SessionRepository,
    SiiGateway,
    StudentRepository,
)
from app.core.errors import (
    InvalidTokenError,
    SessionExpiredError,
    SiiBadResponseError,
    SiiUnauthorizedError,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def jwt_expiry(token: str) -> datetime | None:
    """Read `exp` from the JWT payload without verifying it (SII's secret is not ours)."""
    try:
        payload_part = token.split(".")[1]
        padded = payload_part + "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        exp = payload.get("exp")
        return datetime.fromtimestamp(float(exp), UTC) if exp is not None else None
    except (IndexError, ValueError, TypeError, AttributeError):
        return None


def session_expiry(token: str, now: datetime, ttl_minutes: int) -> datetime:
    """Our rule: the session lasts `ttl_minutes`, never longer than the token itself."""
    expires_at = now + timedelta(minutes=ttl_minutes)
    token_exp = jwt_expiry(token)
    if token_exp is not None and token_exp > now:
        expires_at = min(expires_at, token_exp)
    return expires_at


@dataclass
class LoginResult:
    token: str
    expires_at: datetime
    profile: StudentProfile


class AuthService:
    def __init__(
        self,
        sii: SiiGateway,
        sessions: SessionRepository,
        students: StudentRepository,
        curricula: CurriculumRepository,
        ttl_minutes: int,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._sii = sii
        self._sessions = sessions
        self._students = students
        self._curricula = curricula
        self._ttl = ttl_minutes
        self._clock = clock

    async def login(self, email: str, password: str) -> LoginResult:
        token = await self._sii.login(email.strip(), password)
        try:
            profile = await self._sii.get_profile(token)
        except SiiUnauthorizedError as exc:
            raise SiiBadResponseError("El SII rechazó el token recién emitido.") from exc

        now = self._clock()
        expires_at = session_expiry(token, now, self._ttl)

        await self._sessions.purge_expired(now)
        await self._students.upsert(
            StudentRecord(
                numero_control=profile.numero_control,
                full_name=profile.full_name,
                email=profile.email,
                curriculum_id=await self._curricula.get_active_id(),
                last_login_at=now,
            )
        )
        await self._sessions.create(
            AuthSession(
                token_hash=hash_token(token),
                numero_control=profile.numero_control,
                issued_at=now,
                expires_at=expires_at,
            )
        )
        return LoginResult(token=token, expires_at=expires_at, profile=profile)

    async def authenticate(self, token: str | None) -> AuthenticatedSession:
        if not token:
            raise InvalidTokenError("Falta el token de autorización.")
        token_hash = hash_token(token)
        record = await self._sessions.get(token_hash)
        if record is None:
            raise InvalidTokenError()
        if record.expires_at <= self._clock():
            await self._sessions.delete(token_hash)
            raise SessionExpiredError()
        return AuthenticatedSession(
            token=token,
            token_hash=token_hash,
            numero_control=record.numero_control,
            expires_at=record.expires_at,
        )
