"""Pytest configuration and fixtures"""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db


# Use SQLite for testing (file-based for reliability with async)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    # Import models to register them with SQLModel metadata
    from app.models.user import User  # noqa: F401
    
    # Use file-based SQLite for testing (more reliable than in-memory with async)
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    # Create all tables using SQLModel metadata
    async with engine.begin() as conn:
        from sqlmodel import SQLModel
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        from sqlmodel import SQLModel
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()
    
    # Clean up test database file
    import os
    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests"""
    # Create session maker bound to the test engine
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        # Override the app's database dependency
        async def override_get_db():
            yield session
        
        app.dependency_overrides[get_db] = override_get_db
        
        yield session
        
        # Clean up: rollback any uncommitted changes
        await session.rollback()
        
        # Delete all data from tables (for test isolation)
        from sqlmodel import SQLModel
        for table in reversed(SQLModel.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
        
        # Clear overrides after test
        app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database session override"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_user_verified(db_session: AsyncSession):
    """Create verified test user for login/auth tests"""
    from app.models.user import User
    from app.core.security import get_password_hash
    
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=get_password_hash("testpassword"),
        is_active=True,
        is_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_user_unverified(db_session: AsyncSession):
    """Create unverified test user for email verification tests"""
    from app.models.user import User
    from app.core.security import get_password_hash
    
    user = User(
        email="unverified@example.com",
        username="unverifieduser",
        hashed_password=get_password_hash("testpassword"),
        is_active=True,
        is_verified=False
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# Alias for backward compatibility
test_user = test_user_verified


@pytest.fixture
async def auth_headers(test_user_verified) -> dict:
    """Get authentication headers"""
    from app.core.security import security_manager
    
    access_token, _ = security_manager.create_access_token({"user_id": test_user_verified.id})
    return {"Authorization": f"Bearer {access_token}"}
