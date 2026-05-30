"""Alembic environment configuration - SQLModel (async version)"""
from logging.config import fileConfig
import asyncio
import os
from pathlib import Path
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Load environment variables
from dotenv import load_dotenv
env_file = Path(__file__).parent.parent / "secret" / ".env.development"
if env_file.exists():
    load_dotenv(env_file)

# Import SQLModel Base
from sqlmodel import SQLModel

# Import all models so Alembic can detect them
from app.models.user import User
from app.models.token import RefreshToken, VerificationCode
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk
from app.models.chat import ChatMessage, ChatSession, ChatAttachment, ChatPromptSnapshot
from app.models.wiki import WikiLink, WikiPage, WikiPageRevision, WikiPatch, WikiRun

# Alembic Config object
config = context.config

# Configure logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set MetaData
target_metadata = SQLModel.metadata


# Get database URL from environment variables
def get_url():
    """Get database URL from environment variables"""
    url = os.getenv("DATABASE_URL", "mysql://root:528467@localhost:3306/official_db")
    # Convert to async driver (SQLite doesn't need conversion)
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # SQLite URLs remain unchanged (sqlite:/// or sqlite+aiosqlite:///)
    return url


def run_migrations_offline() -> None:
    """Run migrations in offline mode (sync mode)"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Helper function to execute migrations"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in online mode (async mode)"""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
