"""批量重建知识库文档索引（补齐结构化元数据）"""
import argparse
import asyncio
from typing import List

from sqlmodel import select

from app.core.database import mysql_manager
from app.models.knowledge import Document
from app.services.knowledge import kb_service
from app.core.logger import logger_manager

logger = logger_manager.get_logger(__name__)


async def _load_documents(kb_id: int | None = None, doc_id: int | None = None) -> List[Document]:
    """从数据库读取需要重建的文档列表"""
    await mysql_manager.initialize()
    async with mysql_manager.async_session_maker() as db:
        statement = select(Document)
        if kb_id is not None:
            statement = statement.where(Document.kb_id == kb_id)
        if doc_id is not None:
            statement = statement.where(Document.id == doc_id)
        result = await db.execute(statement)
        return list(result.scalars().all())


async def main() -> None:
    parser = argparse.ArgumentParser(description="重建知识库文档索引（结构化元数据）")
    parser.add_argument("--kb-id", type=int, default=None, help="只重建指定知识库")
    parser.add_argument("--doc-id", type=int, default=None, help="只重建指定文档")
    args = parser.parse_args()

    docs = await _load_documents(kb_id=args.kb_id, doc_id=args.doc_id)
    if not docs:
        logger.info("没有需要重建的文档。")
        await mysql_manager.close()
        return

    logger.info(f"准备重建文档数量：{len(docs)}")
    for doc in docs:
        logger.info(f"开始重建文档：{doc.id} - {doc.file_name}")
        ok = await kb_service.reindex_document(doc.id)
        if ok:
            logger.info(f"重建完成：{doc.id} - {doc.file_name}")
        else:
            logger.warning(f"重建失败或未找到文档：{doc.id}")

    await mysql_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
