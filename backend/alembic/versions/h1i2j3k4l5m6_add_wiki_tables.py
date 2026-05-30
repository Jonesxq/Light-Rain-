"""add wiki tables

Revision ID: h1i2j3k4l5m6
Revises: a7b8c9d0e1f2
Create Date: 2026-05-30 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa


revision = "h1i2j3k4l5m6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("page_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("source_doc_id", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_doc_id"], ["kb_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_pages_kb_path", "wiki_pages", ["kb_id", "path"], unique=True)
    op.create_index(
        "ix_wiki_pages_kb_type", "wiki_pages", ["kb_id", "page_type"], unique=False
    )
    op.create_index(
        "ix_wiki_pages_kb_status", "wiki_pages", ["kb_id", "status"], unique=False
    )
    op.create_index(
        "ix_wiki_pages_source_doc", "wiki_pages", ["source_doc_id"], unique=False
    )
    op.create_index(
        "ix_wiki_pages_created_at", "wiki_pages", ["created_at"], unique=False
    )
    op.create_index(
        "ix_wiki_pages_updated_at", "wiki_pages", ["updated_at"], unique=False
    )

    op.create_table(
        "wiki_page_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.String(length=255), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wiki_page_revisions_page_id",
        "wiki_page_revisions",
        ["page_id"],
        unique=False,
    )
    op.create_index(
        "ix_wiki_page_revisions_kb_path",
        "wiki_page_revisions",
        ["kb_id", "path"],
        unique=False,
    )
    op.create_index(
        "ix_wiki_page_revisions_created_at",
        "wiki_page_revisions",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "wiki_patches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("target_path", sa.String(length=512), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("patch_markdown", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_by_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by_message_id"], ["chat_messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wiki_patches_kb_status",
        "wiki_patches",
        ["kb_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_wiki_patches_target",
        "wiki_patches",
        ["kb_id", "target_path"],
        unique=False,
    )
    op.create_index(
        "ix_wiki_patches_created_at", "wiki_patches", ["created_at"], unique=False
    )

    op.create_table(
        "wiki_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("from_page_id", sa.Integer(), nullable=True),
        sa.Column("from_path", sa.String(length=512), nullable=False),
        sa.Column("to_page_id", sa.Integer(), nullable=True),
        sa.Column("to_path", sa.String(length=512), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False),
        sa.Column("anchor_text", sa.String(length=255), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_page_id"], ["wiki_pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wiki_links_from", "wiki_links", ["kb_id", "from_path"], unique=False
    )
    op.create_index(
        "ix_wiki_links_to", "wiki_links", ["kb_id", "to_path"], unique=False
    )
    op.create_index(
        "ix_wiki_links_type", "wiki_links", ["kb_id", "link_type"], unique=False
    )
    op.create_index(
        "ix_wiki_links_created_at", "wiki_links", ["created_at"], unique=False
    )

    op.create_table(
        "wiki_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=True),
        sa.Column("run_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_id"], ["kb_documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wiki_runs_kb_type", "wiki_runs", ["kb_id", "run_type"], unique=False
    )
    op.create_index(
        "ix_wiki_runs_kb_status", "wiki_runs", ["kb_id", "status"], unique=False
    )
    op.create_index(
        "ix_wiki_runs_created_at", "wiki_runs", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_wiki_links_created_at", table_name="wiki_links")
    op.drop_index("ix_wiki_links_type", table_name="wiki_links")
    op.drop_index("ix_wiki_links_to", table_name="wiki_links")
    op.drop_index("ix_wiki_links_from", table_name="wiki_links")
    op.drop_table("wiki_links")

    op.drop_index("ix_wiki_patches_created_at", table_name="wiki_patches")
    op.drop_index("ix_wiki_patches_target", table_name="wiki_patches")
    op.drop_index("ix_wiki_patches_kb_status", table_name="wiki_patches")
    op.drop_table("wiki_patches")

    op.drop_index(
        "ix_wiki_page_revisions_created_at", table_name="wiki_page_revisions"
    )
    op.drop_index("ix_wiki_page_revisions_kb_path", table_name="wiki_page_revisions")
    op.drop_index("ix_wiki_page_revisions_page_id", table_name="wiki_page_revisions")
    op.drop_table("wiki_page_revisions")

    op.drop_index("ix_wiki_runs_created_at", table_name="wiki_runs")
    op.drop_index("ix_wiki_runs_kb_status", table_name="wiki_runs")
    op.drop_index("ix_wiki_runs_kb_type", table_name="wiki_runs")
    op.drop_table("wiki_runs")

    op.drop_index("ix_wiki_pages_updated_at", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_created_at", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_source_doc", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_status", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_type", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_path", table_name="wiki_pages")
    op.drop_table("wiki_pages")
