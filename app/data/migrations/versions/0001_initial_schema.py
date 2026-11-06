"""Initial schema: curriculum DAG, rules, students, sessions and scenarios.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.orm import UTCDateTime

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "curricula",
    "subjects",
    "requisites",
    "curriculum_rules",
    "students",
    "sessions",
    "scenarios",
)


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "curricula",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("specialty_code", sa.String(40), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("total_credits", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "curriculum_id",
            sa.Integer(),
            sa.ForeignKey("curricula.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("clave", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("ht", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suggested_semester", sa.Integer(), nullable=False),
        sa.Column("grid_row", sa.Integer(), nullable=False),
        sa.Column("grid_col", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="generic"),
        sa.Column("min_credit_pct", sa.Float(), nullable=True),
        sa.Column("counts_toward_load", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("curriculum_id", "clave", name="uq_subject_clave"),
    )
    op.create_table(
        "requisites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "curriculum_id",
            sa.Integer(),
            sa.ForeignKey("curricula.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "requires_subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(16), nullable=False),
        sa.UniqueConstraint("subject_id", "requires_subject_id", name="uq_requisite_pair"),
        sa.CheckConstraint("subject_id <> requires_subject_id", name="ck_requisite_not_self"),
        sa.CheckConstraint("type IN ('prereq', 'coreq')", name="ck_requisite_type"),
    )
    op.create_table(
        "curriculum_rules",
        sa.Column(
            "curriculum_id",
            sa.Integer(),
            sa.ForeignKey("curricula.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("max_credits_per_term", sa.Integer(), nullable=False, server_default="36"),
        sa.Column("min_credits_per_term", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("summer_max_subjects", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("passing_grade", sa.Integer(), nullable=False, server_default="70"),
    )
    op.create_table(
        "students",
        sa.Column("numero_control", sa.String(20), primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column(
            "curriculum_id",
            sa.Integer(),
            sa.ForeignKey("curricula.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_login_at", UTCDateTime(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "numero_control",
            sa.String(20),
            sa.ForeignKey("students.numero_control", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("issued_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False, index=True),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "numero_control",
            sa.String(20),
            sa.ForeignKey("students.numero_control", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("params", _json(), nullable=False),
        sa.Column("result_summary", _json(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
    )

    if op.get_bind().dialect.name == "postgresql":
        # The backend connects as the table owner, so RLS without policies only blocks
        # Supabase's public REST API (anon/authenticated roles) from reading these tables.
        for table in TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
