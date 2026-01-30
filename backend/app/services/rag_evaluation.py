"""RAG 评估服务：基于 RAGas 生成评估集并评估"""
import asyncio
import math
import random
from typing import List, Optional, Tuple

from datasets import Dataset
from langchain_core.documents import Document as LangChainDocument
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_community.embeddings import DashScopeEmbeddings

from ragas import aevaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
try:
    # answer_correctness 版本差异较大，做兼容处理
    from ragas.metrics import answer_correctness
except Exception:
    answer_correctness = None
from ragas.testset import TestsetGenerator
from ragas.run_config import RunConfig

from app.core.config.settings import settings
from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.models.knowledge import Document, DocumentChunk, DocStatus
from app.services.knowledge import kb_service
from app.constant.prompts import RAG_EVAL_ANSWER_PROMPT_TEMPLATE
from sqlmodel import select

logger = logger_manager.get_logger(__name__)


class RagEvaluationService:
    """RAG 评估入口：自动生成样本 -> RAG 回答 -> RAGas 打分"""

    def __init__(self):
        # 服务本身无需额外初始化
        pass

    def _build_llm(self, model_name: Optional[str], temperature: float = 0.2) -> ChatOpenAI:
        """构建 LangChain LLM（统一入口）"""
        return ChatOpenAI(
            model=model_name or settings.llm.DEFAULT_MODEL,
            openai_api_key=settings.llm.QWEN_API_KEY,
            openai_api_base=settings.llm.QWEN_BASE_URL,
            temperature=temperature,
        )

    def _build_embeddings(self) -> DashScopeEmbeddings:
        """构建 Embedding 模型（用于 RAGas）"""
        return DashScopeEmbeddings(
            model=settings.llm.EMBEDDING_MODEL,
            dashscope_api_key=settings.llm.QWEN_API_KEY
        )

    def _build_ragas_llm(self, model_name: Optional[str], temperature: float = 0.2) -> LangchainLLMWrapper:
        """将 LangChain LLM 包装成 RAGas 可用的 LLM"""
        return LangchainLLMWrapper(self._build_llm(model_name, temperature=temperature))

    def _build_ragas_embeddings(self) -> LangchainEmbeddingsWrapper:
        """将 LangChain Embeddings 包装成 RAGas 可用的 Embedding"""
        return LangchainEmbeddingsWrapper(self._build_embeddings())

    async def _load_candidate_chunks(self, kb_id: int, sample_size: int) -> List[DocumentChunk]:
        """加载评估候选切片（限制数量，避免全库扫描）"""
        if sample_size <= 0:
            return []

        # 适当放大候选池，提高问题多样性
        limit = max(sample_size * 5, sample_size)
        limit = min(limit, 200)

        async with mysql_manager.async_session_maker() as db:
            statement = (
                select(DocumentChunk)
                .join(Document, Document.id == DocumentChunk.doc_id)
                .where(Document.kb_id == kb_id, Document.status == DocStatus.COMPLETED)
                .order_by(DocumentChunk.id.desc())
                .limit(limit)
            )
            result = await db.execute(statement)
            chunks = list(result.scalars().all())
        # 过滤过短的切片，避免生成无效问题
        filtered = [c for c in chunks if c.content and len(c.content.strip()) >= 50]
        if not filtered:
            return []

        if len(filtered) <= sample_size:
            return filtered
        return random.sample(filtered, sample_size)

    def _build_langchain_docs(self, chunks: List[DocumentChunk]) -> List[LangChainDocument]:
        """将切片转成 LangChain Document（供 RAGas 生成测试集）"""
        docs: List[LangChainDocument] = []
        for chunk in chunks:
            meta = chunk.structured_meta or {}
            doc_meta = meta.get("doc", {}) if isinstance(meta.get("doc"), dict) else {}
            loc_meta = meta.get("loc", {}) if isinstance(meta.get("loc"), dict) else {}
            file_name = doc_meta.get("file_name") or f"doc_{chunk.doc_id}"
            # RAGas 的 HeadlineSplitter 需要 headlines 字段，缺失会报错
            raw_headlines = loc_meta.get("md_headings")
            if isinstance(raw_headlines, list):
                headlines = [str(h) for h in raw_headlines if str(h).strip()]
            elif isinstance(raw_headlines, str) and raw_headlines.strip():
                headlines = [raw_headlines.strip()]
            else:
                headlines = []

            # RAGas 生成测试集要求 metadata 中包含 filename
            docs.append(
                LangChainDocument(
                    page_content=chunk.content,
                    metadata={
                        "filename": file_name,
                        "doc_id": chunk.doc_id,
                        "headlines": headlines,
                    }
                )
            )
        return docs

    async def _generate_testset(
        self,
        docs: List[LangChainDocument],
        sample_size: int,
        generate_model: Optional[str]
    ):
        """使用 RAGas 生成测试集（无评测集场景）"""
        if not docs:
            return None

        generator_llm = self._build_ragas_llm(generate_model, temperature=0.2)
        generator_embeddings = self._build_ragas_embeddings()
        generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embeddings)

        # 使用预分块入口，避免 HeadlineSplitter 依赖 headlines 字段
        # RAGas 生成是同步流程，放入线程池避免阻塞事件循环
        return await asyncio.to_thread(
            generator.generate_with_chunks,
            docs,
            testset_size=sample_size,
            # 降低并发和重试次数，减少 DashScope 连接不稳定导致的失败
            run_config=RunConfig(max_workers=1, max_retries=2, timeout=60),
            raise_exceptions=False
        )

    def _extract_qa_pairs(self, testset) -> List[Tuple[str, str]]:
        """从 RAGas 测试集中提取问题与参考答案"""
        if not testset:
            return []

        items = testset.to_list()
        pairs: List[Tuple[str, str]] = []
        for item in items:
            question = (item.get("question") or item.get("user_input") or "").strip()
            ground_truth = item.get("ground_truth") or item.get("reference") or ""

            # ground_truth 可能是 list
            if isinstance(ground_truth, list):
                ground_truth = ground_truth[0] if ground_truth else ""
            ground_truth = str(ground_truth).strip()

            if not question or not ground_truth:
                continue
            pairs.append((question, ground_truth))

        return pairs

    async def _answer_with_rag(
        self,
        kb_id: int,
        question: str,
        top_k: int,
        answer_model: Optional[str]
    ) -> Tuple[str, List[str], List[dict]]:
        """用当前 RAG 流程生成回答，并返回上下文列表与来源"""
        context, sources = await kb_service.search_knowledge(
            kb_id=kb_id,
            query=question,
            top_k=top_k
        )

        # 拆分上下文为列表（符合 RAGas contexts 结构）
        contexts = [c.strip() for c in (context or "").split("\n\n") if c.strip()]

        system_prompt = RAG_EVAL_ANSWER_PROMPT_TEMPLATE.format(
            context=context if context else "未找到相关资料。"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question)
        ]

        llm = self._build_llm(answer_model, temperature=0.2)
        response = await llm.ainvoke(messages)
        answer = (getattr(response, "content", "") or "").strip()

        return answer, contexts, sources

    def _safe_float(self, value: object) -> Optional[float]:
        """安全转换为浮点数（过滤 NaN）"""
        try:
            number = float(value)
        except Exception:
            return None
        if math.isnan(number):
            return None
        return number

    def _aggregate_scores(self, score_rows: List[dict]) -> dict:
        """汇总 RAGas 的整体分数"""
        if not score_rows:
            return {}

        metric_names = set()
        for row in score_rows:
            if not isinstance(row, dict):
                continue
            for key, val in row.items():
                if isinstance(val, (int, float)):
                    metric_names.add(key)

        aggregated = {}
        for name in metric_names:
            values = [self._safe_float(row.get(name)) for row in score_rows]
            values = [v for v in values if v is not None]
            aggregated[name] = round(sum(values) / len(values), 3) if values else 0.0

        return aggregated

    def _normalize_score_rows(self, scores) -> List[dict]:
        """兼容不同版本返回的评分结构，统一为 List[dict]"""
        if scores is None:
            return []
        # 已经是 list[dict]
        if isinstance(scores, list):
            normalized = []
            for row in scores:
                if isinstance(row, dict):
                    normalized.append(row)
                else:
                    # 遇到异常结构时直接跳过
                    continue
            return normalized
        # 有些版本可能返回 dict（全局分数）
        if isinstance(scores, dict):
            return [scores]
        return []

    async def evaluate_kb(
        self,
        kb_id: int,
        sample_size: int = 5,
        top_k: int = 4,
        generate_model: Optional[str] = None,
        answer_model: Optional[str] = None,
        judge_model: Optional[str] = None,
        max_chunk_chars: int = 1200
    ) -> dict:
        """对知识库进行自动评估（RAGas 评分）"""
        try:
            # 1) 加载候选切片并构造文档
            chunks = await self._load_candidate_chunks(kb_id, sample_size)
            if not chunks:
                raise ValueError("未找到可用于评估的文档切片，请先确保知识库有已完成的文档。")

            # 2) 构建 LangChain 文档，截断内容长度
            clipped_chunks = []
            for chunk in chunks:
                content = (chunk.content or "").strip()
                if not content:
                    continue
                # 控制输入长度，避免生成过长
                chunk.content = content[:max_chunk_chars]
                clipped_chunks.append(chunk)

            docs = self._build_langchain_docs(clipped_chunks)
            if not docs:
                raise ValueError("评估文档构建失败，请检查切片内容是否为空。")

            # 3) RAGas 生成测试集
            testset = await self._generate_testset(docs, sample_size, generate_model)
            qa_pairs = self._extract_qa_pairs(testset)
            if not qa_pairs:
                raise ValueError("RAGas 未生成有效评测样本，请检查模型连接或文档质量。")

            # 4) 对每个问题进行 RAG 回答
            eval_rows = []
            sources_list = []
            for question, ground_truth in qa_pairs:
                answer, contexts, sources = await self._answer_with_rag(
                    kb_id=kb_id,
                    question=question,
                    top_k=top_k,
                    answer_model=answer_model
                )

                eval_rows.append({
                    "question": question,
                    "answer": answer,
                    "contexts": contexts,
                    # RAGas 期望 reference 为字符串（不同版本字段名不一致，做兼容）
                    "reference": ground_truth,
                    "ground_truth": ground_truth
                })
                sources_list.append(sources)

            if not eval_rows:
                raise ValueError("评估样本为空，无法继续评估。")

            # 5) 构造 RAGas 评估数据集
            dataset = Dataset.from_list(eval_rows)

            # 6) 执行 RAGas 评估
            evaluator_llm = self._build_ragas_llm(judge_model, temperature=0.0)
            evaluator_embeddings = self._build_ragas_embeddings()
            metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
            if answer_correctness is not None:
                metrics.append(answer_correctness)

            try:
                # 使用异步版评估，避免在子线程中反复创建/关闭事件循环
                evaluation_result = await aevaluate(
                    dataset=dataset,
                    metrics=metrics,
                    llm=evaluator_llm,
                    embeddings=evaluator_embeddings,
                    show_progress=False,
                    run_config=RunConfig(max_workers=4)
                )
            except Exception as exc:
                logger.error(f"RAGas evaluate failed: {exc}")
                raise

            # 7) 行级评分与整体均值（兼容不同版本结构）
            score_rows = self._normalize_score_rows(evaluation_result.scores)
            ragas_scores = self._aggregate_scores(score_rows)

            avg_faithfulness = ragas_scores.get("faithfulness", 0.0)
            avg_correctness = ragas_scores.get("answer_correctness", 0.0)
            retrieval_hit_rate = ragas_scores.get("context_recall", 0.0)

            results = []
            for idx, row in enumerate(eval_rows):
                score = score_rows[idx] if idx < len(score_rows) else {}
                if not isinstance(score, dict):
                    score = {}
                results.append({
                    "question": row.get("question"),
                    "reference_answer": row.get("reference") or row.get("ground_truth") or "",
                    "predicted_answer": row.get("answer"),
                    "correctness_score": score.get("answer_correctness"),
                    "faithfulness_score": score.get("faithfulness"),
                    "answer_relevancy_score": score.get("answer_relevancy"),
                    "context_precision_score": score.get("context_precision"),
                    "context_recall_score": score.get("context_recall"),
                    "retrieval_hit": None,
                    "contexts": row.get("contexts"),
                    "ragas_scores": score,
                    "sources": sources_list[idx] if idx < len(sources_list) else []
                })

            return {
                "sample_count": len(eval_rows),
                "avg_correctness": avg_correctness,
                "avg_faithfulness": avg_faithfulness,
                "retrieval_hit_rate": retrieval_hit_rate,
                "ragas_scores": ragas_scores,
                "results": results
            }
        except Exception as exc:
            # 统一抛出异常，方便定位问题
            logger.exception(f"RAG 评估流程失败: {exc}")
            raise


rag_evaluation_service = RagEvaluationService()
