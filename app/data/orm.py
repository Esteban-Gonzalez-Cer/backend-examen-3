"""SQLAlchemy tables (Supabase Postgres). Kept portable so tests can run on SQLite."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator[datetime]):
    """Always hands back timezone-aware UTC datetimes (SQLite drops the offset)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class CurriculumORM(Base):
    __tablename__ = "curricula"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    specialty_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    total_credits: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    subjects: Mapped[list[SubjectORM]] = relationship(back_populates="curriculum")


class SubjectORM(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("curriculum_id", "clave", name="uq_subject_clave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curriculum_id: Mapped[int] = mapped_column(ForeignKey("curricula.id", ondelete="CASCADE"), index=True)
    clave: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    credits: Mapped[int] = mapped_column(Integer)
    ht: Mapped[int] = mapped_column(Integer, default=0)
    hp: Mapped[int] = mapped_column(Integer, default=0)
    suggested_semester: Mapped[int] = mapped_column(Integer)
    grid_row: Mapped[int] = mapped_column(Integer)
    grid_col: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), default="generic")
    min_credit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    counts_toward_load: Mapped[bool] = mapped_column(Boolean, default=True)

    curriculum: Mapped[CurriculumORM] = relationship(back_populates="subjects")


class RequisiteORM(Base):
    __tablename__ = "requisites"
    __table_args__ = (
        UniqueConstraint("subject_id", "requires_subject_id", name="uq_requisite_pair"),
        CheckConstraint("subject_id <> requires_subject_id", name="ck_requisite_not_self"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curriculum_id: Mapped[int] = mapped_column(ForeignKey("curricula.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    requires_subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))

    subject: Mapped[SubjectORM] = relationship(foreign_keys=[subject_id])
    requires: Mapped[SubjectORM] = relationship(foreign_keys=[requires_subject_id])


class CurriculumRulesORM(Base):
    __tablename__ = "curriculum_rules"

    curriculum_id: Mapped[int] = mapped_column(
        ForeignKey("curricula.id", ondelete="CASCADE"), primary_key=True
    )
    max_credits_per_term: Mapped[int] = mapped_column(Integer, default=36)
    min_credits_per_term: Mapped[int] = mapped_column(Integer, default=20)
    summer_max_subjects: Mapped[int] = mapped_column(Integer, default=2)
    passing_grade: Mapped[int] = mapped_column(Integer, default=70)


class StudentORM(Base):
    __tablename__ = "students"

    numero_control: Mapped[str] = mapped_column(String(20), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    curriculum_id: Mapped[int | None] = mapped_column(
        ForeignKey("curricula.id", ondelete="SET NULL"), nullable=True
    )
    last_login_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class SessionORM(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    numero_control: Mapped[str] = mapped_column(
        ForeignKey("students.numero_control", ondelete="CASCADE"), index=True
    )
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    refresh_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScenarioORM(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    numero_control: Mapped[str] = mapped_column(
        ForeignKey("students.numero_control", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JsonType, default=dict)
    result_summary: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
