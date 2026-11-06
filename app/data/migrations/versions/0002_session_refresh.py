"""Sessions: refresh-token hash (HttpOnly cookie) and the SII token encrypted at rest.

Revision ID: 0002_session_refresh
Revises: 0001_initial
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_session_refresh"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sessions created before this migration have no refresh cookie: they keep working with
    # their bearer token until they expire (≤ 30 min), they just can't be restored on reload.
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("refresh_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("token_encrypted", sa.Text(), nullable=True))
    op.create_index("ix_sessions_refresh_hash", "sessions", ["refresh_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sessions_refresh_hash", table_name="sessions")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("token_encrypted")
        batch.drop_column("refresh_hash")
