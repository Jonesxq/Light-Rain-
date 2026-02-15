"""add archived/tags to chat_sessions and create chat_attachments

Revision ID: d1e2f3a4b5c6
Revises: 4c8a1f3d2b7e
Create Date: 2026-02-14 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "4c8a1f3d2b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("tags", sa.JSON(), nullable=True),
    )
    op.alter_column("chat_sessions", "is_archived", server_default=None)
    op.create_index(op.f("ix_chat_sessions_is_archived"), "chat_sessions", ["is_archived"], unique=False)

    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("chunks", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_chat_attachments_user_id"), "chat_attachments", ["user_id"], unique=False)
    op.create_index(op.f("ix_chat_attachments_created_at"), "chat_attachments", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_attachments_created_at"), table_name="chat_attachments")
    op.drop_index(op.f("ix_chat_attachments_user_id"), table_name="chat_attachments")
    op.drop_table("chat_attachments")
    op.drop_index(op.f("ix_chat_sessions_is_archived"), table_name="chat_sessions")
    op.drop_column("chat_sessions", "tags")
    op.drop_column("chat_sessions", "is_archived")
