"""为 kb_doc_chunks 添加 parent_id 字段

Revision ID: b1c2d3e4f5a6
Revises: 5f2d0a8c1b7e
Create Date: 2026-02-07 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "5f2d0a8c1b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_doc_chunks", sa.Column("parent_id", sa.String(length=128), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, doc_id, chunk_index FROM kb_doc_chunks WHERE parent_id IS NULL")
    ).fetchall()
    for row in rows:
        parent_id = f"{row.doc_id}:{row.chunk_index}"
        bind.execute(
            sa.text("UPDATE kb_doc_chunks SET parent_id = :parent_id WHERE id = :id"),
            {"parent_id": parent_id, "id": row.id},
        )

    op.alter_column(
        "kb_doc_chunks",
        "parent_id",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_index(op.f("ix_kb_doc_chunks_parent_id"), "kb_doc_chunks", ["parent_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kb_doc_chunks_parent_id"), table_name="kb_doc_chunks")
    op.drop_column("kb_doc_chunks", "parent_id")

