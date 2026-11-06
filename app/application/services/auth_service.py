"""Login against SII and keep a server-side registry of the issued sessions.

Tokens on the wire:
- access token  = the SII token. The frontend keeps it in memory only and sends it as Bearer.
- refresh token = a random value in an HttpOnly cookie. It survives a page reload and lets the
  frontend get the access token back without the user typing the password again. It never
  outlives the session (≤ SESSION_TTL_MINUTES) and logout deletes it on the server.

The database stores only sha256 hashes of both, plus the SII token encrypted with the server
secret (needed to hand it back on refresh).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.models import (
    AuthenticatedSession,
    AuthSession,
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
from app.core.security import TokenCipher, hash_token, new_refresh_token

def utcnow() -> datetime:
    return datetime.now(UTC)


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
class SessionGrant:
    """What login and refresh hand to the interaction layer."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    numero_control: str
    full_name: str
    email: str


class AuthService:
    def __init__(
        self,
        sii: SiiGateway,
        sessions: SessionRepository,
        students: StudentRepository,
        curricula: CurriculumRepository,
        ttl_minutes: int,
        cipher: TokenCipher,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._sii = sii
        self._sessions = sessions
        self._students = students
        self._curricula = curricula
        self._ttl = ttl_minutes
        self._cipher = cipher
        self._clock = clock

    async def login(self, email: str, password: str) -> SessionGrant:
        token = await self._sii.login(email.strip(), password)
        try:
            profile = await self._sii.get_profile(token)
        except SiiUnauthorizedError as exc:
            raise SiiBadResponseError("El SII rechazó el token recién emitido.") from exc

        now = self._clock()
        expires_at = session_expiry(token, now, self._ttl)
        refresh_token = new_refresh_token()

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
                refresh_hash=hash_token(refresh_token),
                token_encrypted=self._cipher.encrypt(token),
            )
        )
        return SessionGrant(
            access_token=token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            numero_control=profile.numero_control,
            full_name=profile.full_name,
            email=profile.email,
        )

    async def refresh(self, refresh_token: str | None) -> SessionGrant:
        """Give the access token back to a reloaded page that still holds the refresh cookie.

        It never extends the session: `expires_at` stays the one fixed at login.
        """
        if not refresh_token:
            raise InvalidTokenError("No hay una sesión que restaurar.")
        record = await self._sessions.get_by_refresh(hash_token(refresh_token))
        if record is None:
            raise InvalidTokenError()
        if record.expires_at <= self._clock():
            await self._sessions.delete(record.token_hash)
            raise SessionExpiredError()

        token = self._cipher.decrypt(record.token_encrypted) if record.token_encrypted else None
        student = await self._students.get(record.numero_control)
        if token is None or hash_token(token) != record.token_hash or student is None:
            # Encrypted with another SESSION_SECRET (or tampered with): the session is unusable.
            await self._sessions.delete(record.token_hash)
            raise InvalidTokenError()

        return SessionGrant(
            access_token=token,
            refresh_token=refresh_token,
            expires_at=record.expires_at,
            numero_control=student.numero_control,
            full_name=student.full_name,
            email=student.email,
        )

    async def logout(self, refresh_token: str | None, access_token: str | None) -> None:
        """Revoke the session on the server. Idempotent: logging out twice is not an error."""
        if refresh_token:
            record = await self._sessions.get_by_refresh(hash_token(refresh_token))
            if record is not None:
                await self._sessions.delete(record.token_hash)
        if access_token:
            await self._sessions.delete(hash_token(access_token))

    def remaining_seconds(self, expires_at: datetime) -> int:
        return max(0, int((expires_at - self._clock()).total_seconds()))

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
