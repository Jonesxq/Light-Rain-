import asyncio
from sqlmodel import select
from app.core.database import db_manager, mysql_manager
from app.models.knowledge import KnowledgeBase

async def list_kb():
    await mysql_manager.initialize()
    async with mysql_manager.async_session_maker() as session:
        statement = select(KnowledgeBase)
        result = await session.execute(statement)
        kbs = result.scalars().all()
        print("\nAvailable Knowledge Bases:")
        for kb in kbs:
            print(f"ID: {kb.id}, Name: {kb.name}")

if __name__ == "__main__":
    asyncio.run(list_kb())
