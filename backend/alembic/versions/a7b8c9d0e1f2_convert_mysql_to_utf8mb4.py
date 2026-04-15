"""convert mysql charset to utf8mb4

Revision ID: a7b8c9d0e1f2
Revises: f4a5b6c7d8e9
Create Date: 2026-04-15 00:00:00.000000+00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    # 1) 先把当前数据库默认字符集切到 utf8mb4，保证后续新建表/列默认正确。
    db_name = bind.execute(sa.text("SELECT DATABASE()")).scalar()
    if db_name:
        safe_db_name = str(db_name).replace("`", "``")
        op.execute(
            sa.text(
                f"ALTER DATABASE `{safe_db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )

    # 2) 把所有业务表转成 utf8mb4，修复现有 utf8mb3 列无法写入 emoji 的问题。
    inspector = sa.inspect(bind)
    for table_name in inspector.get_table_names():
        safe_table_name = table_name.replace("`", "``")
        op.execute(
            sa.text(
                f"ALTER TABLE `{safe_table_name}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )


def downgrade() -> None:
    # 不回退字符集，避免把 4-byte 字符数据降级为不可表示状态。
    pass

