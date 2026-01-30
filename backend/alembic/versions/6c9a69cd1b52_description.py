"""初始化基础表结构

Revision ID: 6c9a69cd1b52
Revises: 
Create Date: 2026-01-18 05:41:20.455125+00:00

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# 修订版本标识（Alembic 使用）
revision = '6c9a69cd1b52'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### Alembic 自动生成命令 ###
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_superuser', sa.Boolean(), nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('device_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('device_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
    sa.Column('ip_address', sqlmodel.sql.sqltypes.AutoString(length=45), nullable=True),
    sa.Column('user_agent', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('is_revoked', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_expires_at'), 'refresh_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_is_revoked'), 'refresh_tokens', ['is_revoked'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_token'), 'refresh_tokens', ['token'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('verification_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('code_type', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('is_used', sa.Boolean(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_verification_codes_code'), 'verification_codes', ['code'], unique=False)
    op.create_index(op.f('ix_verification_codes_code_type'), 'verification_codes', ['code_type'], unique=False)
    op.create_index(op.f('ix_verification_codes_expires_at'), 'verification_codes', ['expires_at'], unique=False)
    op.create_index(op.f('ix_verification_codes_is_used'), 'verification_codes', ['is_used'], unique=False)
    op.create_index(op.f('ix_verification_codes_user_id'), 'verification_codes', ['user_id'], unique=False)
    # ### Alembic 自动生成命令结束 ###


def downgrade() -> None:
    # ### Alembic 自动生成命令 ###
    op.drop_index(op.f('ix_verification_codes_user_id'), table_name='verification_codes')
    op.drop_index(op.f('ix_verification_codes_is_used'), table_name='verification_codes')
    op.drop_index(op.f('ix_verification_codes_expires_at'), table_name='verification_codes')
    op.drop_index(op.f('ix_verification_codes_code_type'), table_name='verification_codes')
    op.drop_index(op.f('ix_verification_codes_code'), table_name='verification_codes')
    op.drop_table('verification_codes')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_is_revoked'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_expires_at'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    # ### Alembic 自动生成命令结束 ###
