"""sandbox script code: loại test 'script', projects.script_enabled

Revision ID: 0004_sandbox
Revises: 0003_phase5
Create Date: 2026-10-16 06:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_sandbox"
down_revision: str | Sequence[str] | None = "0003_phase5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_VALUES = "'api', 'web', 'desktop_macos', 'desktop_windows', 'mobile_android', 'mobile_ios'"


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE không chạy được trong transaction trên PostgreSQL cũ, tách riêng cho chắc.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE test_type ADD VALUE IF NOT EXISTS 'script'")
    op.add_column(
        "projects",
        sa.Column("script_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    conn = op.get_bind()
    used = conn.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM test_cases WHERE test_type = 'script')"
            " + (SELECT count(*) FROM test_run_items WHERE test_type = 'script')"
        )
    ).scalar()
    if used:
        raise RuntimeError(
            f"Còn {used} test case/kết quả loại script; xuất hoặc xóa chúng trước khi hạ phiên bản"
        )
    op.drop_column("projects", "script_enabled")
    op.execute("ALTER TYPE test_type RENAME TO test_type_old")
    op.execute(f"CREATE TYPE test_type AS ENUM ({OLD_VALUES})")
    for table in ("test_cases", "test_run_items"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN test_type TYPE test_type"
            " USING test_type::text::test_type"
        )
    op.execute("DROP TYPE test_type_old")
