from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.models import AuthSession, StudentRecord
from app.data.orm import SessionORM, StudentORM


class SqlSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, session: AuthSession) -> None:
        existing = await self._db.get(SessionORM, session.token_hash)
        if existing is not None:
            existing.issued_at = session.issued_at
            existing.expires_at = session.expires_at
        else:
            self._db.add(
                SessionORM(
                    token_hash=session.token_hash,
                    numero_control=session.numero_control,
                    issued_at=session.issued_at,
                    expires_at=session.expires_at,
                )
            )
        await self._db.commit()

    async def get(self, token_hash: str) -> AuthSession | None:
        row = await self._db.get(SessionORM, token_hash)
        if row is None:
            return None
        return AuthSession(
            token_hash=row.token_hash,
            numero_control=row.numero_control,
            issued_at=row.issued_at,
            expires_at=row.expires_at,
        )

    async def delete(self, token_hash: str) -> None:
        await self._db.execute(delete(SessionORM).where(SessionORM.token_hash == token_hash))
        await self._db.commit()

    async def purge_expired(self, now: datetime) -> int:
        result = await self._db.execute(delete(SessionORM).where(SessionORM.expires_at <= now))
        await self._db.commit()
        return result.rowcount or 0


class SqlStudentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(self, record: StudentRecord) -> None:
        row = (
            await self._db.execute(
                select(StudentORM).where(StudentORM.numero_control == record.numero_control)
            )
        ).scalar_one_or_none()
        if row is None:
            self._db.add(
                StudentORM(
                    numero_control=record.numero_control,
                    full_name=record.full_name,
                    email=record.email,
                    curriculum_id=record.curriculum_id,
                    last_login_at=record.last_login_at,
                )
            )
        else:
            row.full_name = record.full_name
            row.email = record.email
            row.curriculum_id = record.curriculum_id
            row.last_login_at = record.last_login_at
        await self._db.commit()
