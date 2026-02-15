"""backfill chat session tags

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-02-15 00:00:00.000000+00:00

"""
from alembic import op


revision = "f4a5b6c7d8e9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 将历史 NULL tags 回填为 []
    op.execute("UPDATE chat_sessions SET tags='[]' WHERE tags IS NULL")


def downgrade() -> None:
    # 回退为 NULL（尽量保持可逆）
    op.execute("UPDATE chat_sessions SET tags=NULL WHERE tags='[]'")
