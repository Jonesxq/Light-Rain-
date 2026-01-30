"""为 chat_messages 添加 sources 字段

Revision ID: 5f2d0a8c1b7e
Revises: 9b3f4f1d2c9a
Create Date: 2026-01-29 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


# 修订版本标识（Alembic 使用）
revision = "5f2d0a8c1b7e"
down_revision = "9b3f4f1d2c9a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加 sources 字段（JSON）
    op.add_column("chat_messages", sa.Column("sources", sa.JSON(), nullable=True))


def downgrade() -> None:
    # 回滚：删除 sources 字段
    op.drop_column("chat_messages", "sources")
