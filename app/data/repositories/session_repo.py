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
            existing.refresh_hash = session.refresh_hash
            existing.token_encrypted = session.token_encrypted
        else:
            self._db.add(
                SessionORM(
                    token_hash=session.token_hash,
                    numero_control=session.numero_control,
                    issued_at=session.issued_at,
                    expires_at=session.expires_at,
                    refresh_hash=session.refresh_hash,
                    token_encrypted=session.token_encrypted,
                )
            )
        await self._db.commit()

    async def get(self, token_hash: str) -> AuthSession | None:
        row = await self._db.get(SessionORM, token_hash)
        return _to_domain(row) if row is not None else None

    async def get_by_refresh(self, refresh_hash: str) -> AuthSession | None:
        row = (
            await self._db.execute(select(SessionORM).where(SessionORM.refresh_hash == refresh_hash))
        ).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def delete(self, token_hash: str) -> None:
        await self._db.execute(delete(SessionORM).where(SessionORM.token_hash == token_hash))
        await self._db.commit()

    async def purge_expired(self, now: datetime) -> int:
        result = await self._db.execute(delete(SessionORM).where(SessionORM.expires_at <= now))
        await self._db.commit()
        return result.rowcount or 0


def _to_domain(row: SessionORM) -> AuthSession:
    return AuthSession(
        token_hash=row.token_hash,
        numero_control=row.numero_control,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        refresh_hash=row.refresh_hash,
        token_encrypted=row.token_encrypted,
    )


class SqlStudentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, numero_control: str) -> StudentRecord | None:
        row = await self._db.get(StudentORM, numero_control)
        if row is None:
            return None
        return StudentRecord(
            numero_control=row.numero_control,
            full_name=row.full_name,
            email=row.email,
            curriculum_id=row.curriculum_id,
            last_login_at=row.last_login_at,
        )

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
