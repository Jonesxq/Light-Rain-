"""空迁移占位

Revision ID: 0ae0581e52c4
Revises: 6c9a69cd1b52
Create Date: 2026-01-18 12:52:53.102013+00:00

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# 修订版本标识（Alembic 使用）
revision = '0ae0581e52c4'
down_revision = '6c9a69cd1b52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### Alembic 自动生成命令 ###
    pass
    # ### Alembic 自动生成命令结束 ###


def downgrade() -> None:
    # ### Alembic 自动生成命令 ###
    pass
    # ### Alembic 自动生成命令结束 ###
