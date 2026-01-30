"""为 chat_messages 添加 kb_id 字段

Revision ID: eb81978dcc2e
Revises: 0ae0581e52c4
Create Date: 2026-01-19 04:59:36.164847+00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'eb81978dcc2e'
down_revision = '0ae0581e52c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 安全升级：仅在列不存在时添加 kb_id 字段
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("chat_messages"):
        return

    columns = [col["name"] for col in inspector.get_columns("chat_messages")]
    if "kb_id" not in columns:
        op.add_column("chat_messages", sa.Column("kb_id", sa.Integer(), nullable=True))

    # 创建索引（如果不存在）
    index_exists = False
    for idx in inspector.get_indexes("chat_messages"):
        if idx.get("column_names") == ["kb_id"]:
            index_exists = True
            break
    if not index_exists:
        op.create_index(op.f("ix_chat_messages_kb_id"), "chat_messages", ["kb_id"], unique=False)

    # 创建外键（如果 knowledge_bases 表存在且未建立）
    if inspector.has_table("knowledge_bases"):
        fk_exists = False
        for fk in inspector.get_foreign_keys("chat_messages"):
            if fk.get("referred_table") == "knowledge_bases" and fk.get("constrained_columns") == ["kb_id"]:
                fk_exists = True
                break
        if not fk_exists:
            op.create_foreign_key(
                "chat_messages_kb_id_fkey",
                "chat_messages",
                "knowledge_bases",
                ["kb_id"],
                ["id"],
            )


def downgrade() -> None:
    # 回滚：移除 kb_id 列（若存在）
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("chat_messages"):
        return

    # 删除外键（如果存在）
    for fk in inspector.get_foreign_keys("chat_messages"):
        if fk.get("referred_table") == "knowledge_bases" and fk.get("constrained_columns") == ["kb_id"]:
            op.drop_constraint(fk.get("name"), "chat_messages", type_="foreignkey")
            break

    # 删除索引（如果存在）
    for idx in inspector.get_indexes("chat_messages"):
        if idx.get("column_names") == ["kb_id"]:
            op.drop_index(idx.get("name"), table_name="chat_messages")
            break

    columns = [col["name"] for col in inspector.get_columns("chat_messages")]
    if "kb_id" in columns:
        op.drop_column("chat_messages", "kb_id")
