"""查询改写服务：优化用户查询以提升检索效果"""
import re
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.constant.prompts import QUERY_REWRITE_SYSTEM_PROMPT
from app.services.shared.llm_runtime import llm_runtime_service
from app.services.shared.usage import UsageTimer
from app.utils.llm_factory import build_chat_llm

logger = logger_manager.get_logger(__name__)

# 常见专业术语缩写 -> 中文全称（可按需扩展）
_ABBREVIATION_MAP = {
    "AI": "人工智能",
    "RAG": "检索增强生成",
    "LLM": "大语言模型",
    "NLP": "自然语言处理",
    "CV": "计算机视觉",
    "OCR": "光学字符识别",
    "AIGC": "人工智能生成内容",
    "AGI": "通用人工智能",
    "API": "应用程序接口",
    "SDK": "软件开发工具包",
}


class QueryRewriteService:
    """查询改写服务：优化用户查询以提升检索效果"""
    
    def __init__(self) -> None:
        """初始化查询改写服务（模型在调用时才实例化）"""
        # 仅在调用时实例化模型，便于环境切换与故障降级
        pass

    def _get_llm(self) -> ChatOpenAI:
        """获取LLM实例"""
        return build_chat_llm(
            model=settings.llm.QUERY_REWRITE_MODEL,
            temperature=0.0,
            streaming=False,
        )

    def _clean_rewrite(self, text: str) -> str:
        """清理改写后的文本"""
        if not text:
            return ""
        # 去掉可能的前缀
        cleaned = re.sub(r"^(改写|重写|问题)[:：]\s*", "", text.strip())
        # 只取第一行，避免多行输出
        cleaned = cleaned.splitlines()[0].strip()
        return cleaned

    def _expand_abbreviations(self, text: str) -> str:
        """扩展常见专业术语缩写"""
        if not text:
            return text

        expanded = text
        for abbr, full in _ABBREVIATION_MAP.items():
            # 如果已包含"缩写（全称）"或"缩写(全称)"，就不重复添加
            already = re.search(rf"{abbr}\s*[\(（]{re.escape(full)}[\)）]", expanded, flags=re.IGNORECASE)
            if already:
                continue

            # 仅替换独立缩写，避免误伤长单词内部
            pattern = rf"(?<![A-Za-z0-9]){abbr}(?![A-Za-z0-9])"
            expanded = re.sub(
                pattern,
                f"{abbr}（{full}）",
                expanded,
                flags=re.IGNORECASE
            )

        return expanded

    def _is_non_rewrite_signal(self, text: str) -> bool:
        """检查是否为非改写信号"""
        if not text:
            return False
        lowered = text.strip().lower()
        # 常见的非改写提示语
        patterns = [
            "不需要", "无需改写", "不改写", "无需", "不用改写",
            "no", "n/a", "false", "否"
        ]
        return any(p in lowered for p in patterns)

    async def rewrite_query(self, query: str, user_id: int | None = None, kb_id: int | None = None, db: AsyncSession | None = None) -> str:
        """改写用户查询
        
        Args:
            query: 原始查询
            user_id: 用户ID（可选，用于记录使用量）
            kb_id: 知识库ID（可选，用于记录使用量）
            db: 数据库会话（可选，用于记录使用量）
            
        Returns:
            改写后的查询
        """
        if not query or not query.strip():
            return query

        try:
            llm = self._get_llm()
            messages = [
                SystemMessage(content=QUERY_REWRITE_SYSTEM_PROMPT),
                HumanMessage(content=query.strip()),
            ]
            timer = UsageTimer()
            response = await llm.ainvoke(messages)
            latency_ms = timer.stop_ms()
            usage = llm_runtime_service.finalize_usage(
                llm=llm,
                messages=messages,
                output_text=getattr(response, "content", "") or "",
                payload=response,
            )
            await llm_runtime_service.record_success(
                db=db,
                user_id=user_id,
                event_type="query_rewrite",
                model_name=llm.model_name,
                usage=usage,
                latency_ms=latency_ms,
                metadata={"kb_id": kb_id} if kb_id is not None else None,
            )
            rewritten = self._clean_rewrite(getattr(response, "content", "") or "")
            # 如果模型输出"无需改写"之类的提示，则回退原问题
            if self._is_non_rewrite_signal(rewritten):
                return self._expand_abbreviations(query)
            # 统一做缩写扩展，保证专业术语可理解
            return self._expand_abbreviations(rewritten or query)
        except Exception as e:
            if user_id is not None:
                try:
                    await llm_runtime_service.record_failure(
                        db=db,
                        user_id=user_id,
                        event_type="query_rewrite",
                        model_name=None,
                        error=e,
                        latency_ms=None,
                        metadata={"kb_id": kb_id} if kb_id is not None else None,
                    )
                except Exception:
                    pass
            # 改写失败时直接回退原问题，保证主流程可用
            logger.warning(f"Query rewrite failed, fallback to original: {e}")
            return self._expand_abbreviations(query)


# 单例实例
query_rewrite_service = QueryRewriteService()
