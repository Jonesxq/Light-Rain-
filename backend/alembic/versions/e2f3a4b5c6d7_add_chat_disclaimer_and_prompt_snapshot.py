"""add chat disclaimers and prompt snapshots

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-02-15 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = {t.lower() for t in inspector.get_table_names()}

    if "chat_messages" in tables:
        columns = {c["name"].lower() for c in inspector.get_columns("chat_messages")}
        if "disclaimer_codes" not in columns:
            op.add_column(
                "chat_messages",
                sa.Column("disclaimer_codes", sa.JSON(), nullable=True),
            )
        if "risk_tags" not in columns:
            op.add_column(
                "chat_messages",
                sa.Column("risk_tags", sa.JSON(), nullable=True),
            )

    if "chat_prompt_snapshots" not in tables:
        op.create_table(
            "chat_prompt_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False),
            sa.Column("mode", sa.String(length=30), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    existing_indexes = set()
    if "chat_prompt_snapshots" in tables:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("chat_prompt_snapshots")}

    index_specs = [
        ("ix_chat_prompt_snapshots_message_id", ["message_id"]),
        ("ix_chat_prompt_snapshots_user_id", ["user_id"]),
        ("ix_chat_prompt_snapshots_session_id", ["session_id"]),
        ("ix_chat_prompt_snapshots_created_at", ["created_at"]),
    ]
    for name, cols in index_specs:
        if name not in existing_indexes:
            op.create_index(name, "chat_prompt_snapshots", cols, unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_prompt_snapshots_created_at"), table_name="chat_prompt_snapshots")
    op.drop_index(op.f("ix_chat_prompt_snapshots_session_id"), table_name="chat_prompt_snapshots")
    op.drop_index(op.f("ix_chat_prompt_snapshots_user_id"), table_name="chat_prompt_snapshots")
    op.drop_index(op.f("ix_chat_prompt_snapshots_message_id"), table_name="chat_prompt_snapshots")
    op.drop_table("chat_prompt_snapshots")
    op.drop_column("chat_messages", "risk_tags")
    op.drop_column("chat_messages", "disclaimer_codes")
