"""Add user LLM settings table

Revision ID: c8d9e0f1a2b3
Revises: b1c2d3e4f5a6
Create Date: 2026-02-09 00:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_llm_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=10), nullable=True),
        sa.Column("api_base_url", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_llm_settings_user_id", "user_llm_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_llm_settings_user_id", table_name="user_llm_settings")
    op.drop_table("user_llm_settings")
