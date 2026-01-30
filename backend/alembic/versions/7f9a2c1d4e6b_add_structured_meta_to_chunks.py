"""为 kb_doc_chunks 添加 structured_meta 字段

Revision ID: 7f9a2c1d4e6b
Revises: 2f7c1f2a6f3b
Create Date: 2026-01-29 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f9a2c1d4e6b"
down_revision = "2f7c1f2a6f3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加结构化元数据字段（JSON）
    op.add_column("kb_doc_chunks", sa.Column("structured_meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    # 回滚：删除结构化元数据字段
    op.drop_column("kb_doc_chunks", "structured_meta")
