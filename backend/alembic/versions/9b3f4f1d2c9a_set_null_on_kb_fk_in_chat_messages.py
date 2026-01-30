"""知识库外键删除策略改为 SET NULL

Revision ID: 9b3f4f1d2c9a
Revises: 7f9a2c1d4e6b
Create Date: 2026-01-29 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


# 修订版本标识（Alembic 使用）
revision = "9b3f4f1d2c9a"
down_revision = "7f9a2c1d4e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除旧外键（如果存在）
    try:
        op.drop_constraint("chat_messages_ibfk_2", "chat_messages", type_="foreignkey")
    except Exception:
        # 兼容不同命名的外键
        pass

    # 重新创建为 ON DELETE SET NULL
    op.create_foreign_key(
        "chat_messages_kb_id_fkey",
        "chat_messages",
        "knowledge_bases",
        ["kb_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 回滚：移除 SET NULL 外键，恢复无级联
    try:
        op.drop_constraint("chat_messages_kb_id_fkey", "chat_messages", type_="foreignkey")
    except Exception:
        pass

    op.create_foreign_key(
        "chat_messages_ibfk_2",
        "chat_messages",
        "knowledge_bases",
        ["kb_id"],
        ["id"],
    )
