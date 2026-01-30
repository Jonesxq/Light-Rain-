"""为用户相关外键添加级联删除

Revision ID: 2f7c1f2a6f3b
Revises: eb81978dcc2e
Create Date: 2026-01-27 09:58:00.000000+00:00

"""
from alembic import op


# 修订版本标识（Alembic 使用）
revision = "2f7c1f2a6f3b"
down_revision = "eb81978dcc2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除已有外键约束
    op.drop_constraint("verification_codes_ibfk_1", "verification_codes", type_="foreignkey")
    op.drop_constraint("refresh_tokens_ibfk_1", "refresh_tokens", type_="foreignkey")

    # 重新创建为 ON DELETE CASCADE
    op.create_foreign_key(
        "verification_codes_ibfk_1",
        "verification_codes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "refresh_tokens_ibfk_1",
        "refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 回滚：去掉级联删除
    op.drop_constraint("verification_codes_ibfk_1", "verification_codes", type_="foreignkey")
    op.drop_constraint("refresh_tokens_ibfk_1", "refresh_tokens", type_="foreignkey")

    # 恢复普通外键
    op.create_foreign_key(
        "verification_codes_ibfk_1",
        "verification_codes",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "refresh_tokens_ibfk_1",
        "refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
    )
