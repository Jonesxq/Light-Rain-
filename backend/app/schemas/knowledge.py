from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class KnowledgeBaseCreate(BaseModel):
    """创建知识库的请求体"""
    # 知识库名称
    name: str = Field(..., example="我的专业文档库")
    # 知识库描述（可选）
    description: Optional[str] = Field(None, example="存储合同、技术文档等")


class KnowledgeBaseResponse(BaseModel):
    """返回给前端的知识库信息"""
    # 知识库 ID
    id: int
    # 知识库名称
    name: str
    # 所属用户 ID
    user_id: int
    # 创建时间
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    """返回给前端的文档信息"""
    # 文档 ID
    id: int
    # 文件名
    file_name: str
    # 处理状态（completed / failed / processing）
    status: str
    # 分块数量
    chunk_count: int
    # 创建时间
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeEvalRequest(BaseModel):
    """知识库评估请求体（无评测集时自动生成）"""
    # 评估样本数量
    sample_size: int = Field(5, ge=1, le=50)
    # RAG 检索 top_k
    top_k: int = Field(2, ge=1, le=20)
    # 生成问题与参考答案的模型（可选）
    generate_model: Optional[str] = None
    # 回答问题的模型（可选）
    answer_model: Optional[str] = None
    # 评审评分的模型（可选）
    judge_model: Optional[str] = None
    # 单条 chunk 最大截断长度
    max_chunk_chars: int = Field(1200, ge=200, le=4000)


class KnowledgeEvalSample(BaseModel):
    """单条评估结果"""
    # 评估问题
    question: str
    # 参考答案
    reference_answer: str
    # RAG 输出答案
    predicted_answer: str
    # 正确性评分（0-5）
    correctness_score: Optional[float] = None
    # 忠实性评分（0-5）
    faithfulness_score: Optional[float] = None
    # 回答相关性评分（可选）
    answer_relevancy_score: Optional[float] = None
    # 上下文精确率评分（可选）
    context_precision_score: Optional[float] = None
    # 上下文召回率评分（可选）
    context_recall_score: Optional[float] = None
    # 评审原因（可选）
    judge_reason: Optional[str] = None
    # 是否命中原始 chunk
    retrieval_hit: Optional[bool] = None
    # 实际用于评估的上下文
    contexts: Optional[List[str]] = None
    # RAGas 原始评分（可选）
    ragas_scores: Optional[dict] = None
    # 引用来源（可选，结构化字典列表）
    sources: Optional[List[dict]] = None


class KnowledgeEvalResponse(BaseModel):
    """知识库评估响应体"""
    # 评估样本数量
    sample_count: int
    # 平均正确性分数
    avg_correctness: float
    # 平均忠实性分数
    avg_faithfulness: float
    # 检索命中率
    retrieval_hit_rate: float
    # RAGas 总体评分
    ragas_scores: Optional[dict] = None
    # 明细结果
    results: List[KnowledgeEvalSample]
