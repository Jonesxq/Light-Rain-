"""add is_favorite and edited_at to chat_messages

Revision ID: 4c8a1f3d2b7e
Revises: c8d9e0f1a2b3
Create Date: 2026-02-14 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


revision = "4c8a1f3d2b7e"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "chat_messages",
        sa.Column("edited_at", sa.DateTime(), nullable=True),
    )
    op.alter_column("chat_messages", "is_favorite", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_messages", "edited_at")
    op.drop_column("chat_messages", "is_favorite")
