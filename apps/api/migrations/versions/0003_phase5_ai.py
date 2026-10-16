"""phase5 ai: projects.ai_enabled

Revision ID: 0003_phase5
Revises: 0002_phase3
Create Date: 2026-10-16 05:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase5"
down_revision: str | Sequence[str] | None = "0002_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("ai_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("projects", "ai_enabled")
