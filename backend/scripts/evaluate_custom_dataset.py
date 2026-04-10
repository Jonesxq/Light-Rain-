import asyncio
import json
import argparse
from datasets import Dataset

from ragas import aevaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.core.database import db_manager
from app.core.redis import redis_manager
from app.services.rag_evaluation import rag_evaluation_service

logger = logger_manager.get_logger(__name__)

async def run_custom_evaluation(kb_id: int, dataset_path: str):
    logger.info(f"开始加载外部测试集: {dataset_path}")
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"无法读取文件: {e}")
        return

    eval_rows = []
    
    for i, item in enumerate(data):
        question = item.get("question")
        ground_truth = item.get("ground_truth")
        
        if not question or not ground_truth:
            logger.warning(f"行 {i} 数据缺失 question 或 ground_truth，跳过。")
            continue
            
        logger.info(f"[{i+1}/{len(data)}] 系统正在调用检索生成回答 -> {question}")
        
        # 巧妙地复用了系统中处理 RAG QA 流程、拼装上下文的方法
        answer, contexts, sources = await rag_evaluation_service._answer_with_rag(
            kb_id=kb_id,
            question=question,
            top_k=4,  # 可根据需求更改
            answer_model=settings.llm.DEFAULT_MODEL
        )
        
        eval_rows.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": ground_truth,
            "reference": ground_truth,  # 兼容部分版本里的字段名要求
        })

    if not eval_rows:
        logger.error("无有效的评测数据。")
        return

    logger.info(f"生成完毕。总计 {len(eval_rows)} 条待评测数据。交由 RAGas 进行算子打分...")
    
    dataset = Dataset.from_list(eval_rows)
    
    # 构建包裹着系统原生 LLM 和 Embedding 的 RAGas Provider
    evaluator_llm = rag_evaluation_service._build_ragas_llm(model_name=None, temperature=0.0)
    evaluator_embeddings = rag_evaluation_service._build_ragas_embeddings()
    # 评判指标配置
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    
    result = await aevaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        show_progress=True,
    )
    
    logger.info(f"============ RAGas 总计分 ============\n{result}")
    
    output_report = "ragas_evaluation_report.json"
    df = result.to_pandas()
    df.to_json(output_report, orient="records", force_ascii=False, indent=2)
    logger.info(f"详细单条试题分析和打分报告已保存至 {output_report}")


async def main(kb_id: int, dataset_path: str):
    logger.info("正在初始化底层数据库和 Redis 连接...")
    await db_manager.initialize()
    await redis_manager.initialize_async()
    try:
        await run_custom_evaluation(kb_id, dataset_path)
    finally:
        await db_manager.close()
        await redis_manager.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="外部数据集 RAGas 评估向导")
    parser.add_argument("--kb_id", type=int, required=True, help="知识库ID(对应您的应用系统内该知识库的主键)")
    parser.add_argument("--dataset", type=str, required=True, help="包含问答的JSON格式数据集绝对或相对路径")
    
    args = parser.parse_args()
    asyncio.run(main(args.kb_id, args.dataset))
