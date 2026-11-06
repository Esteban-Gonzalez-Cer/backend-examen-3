"""Shared handling for SII calls made on behalf of an authenticated session."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from app.application.models import AuthenticatedSession
from app.application.ports import SessionRepository
from app.core.errors import SessionExpiredError, SiiUnauthorizedError

T = TypeVar("T")


async def guarded(sessions: SessionRepository, auth: AuthenticatedSession, call: Awaitable[T]) -> T:
    """If SII rejects the token, forget our session too and report it as expired."""
    try:
        return await call
    except SiiUnauthorizedError as exc:
        await sessions.delete(auth.token_hash)
        raise SessionExpiredError() from exc
