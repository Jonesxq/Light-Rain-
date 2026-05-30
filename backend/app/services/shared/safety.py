"""安全与合规检测服务"""

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.constant.prompts import SAFETY_CLASSIFY_PROMPT
from app.utils.llm_factory import build_chat_llm
from app.utils.json_utils import parse_json_obj
from app.core.logger import logger_manager


logger = logger_manager.get_logger(__name__)

# 风险关键词定义
RISK_KEYWORDS = {
    "medical": [
        "医疗", "医生", "诊断", "治疗", "药", "处方", "病症", "症状", "癌", "肿瘤",
        "手术", "用药", "剂量", "副作用", "检查", "就医", "病历",
    ],
    "legal": [
        "法律", "律师", "诉讼", "合同", "起诉", "判决", "责任", "仲裁",
        "法规", "合规", "侵权", "刑法", "民法", "行政处罚", "劳动法",
    ],
    "financial": [
        "投资", "理财", "股票", "基金", "债券", "收益", "回报", "风险",
        "交易", "资产", "币", "期货", "外汇", "贷款", "利率", "金融",
    ],
}

# 允许的标签集合
ALLOWED_LABELS = {"medical", "legal", "financial"}


def _keyword_detect(text: str) -> list[str]:
    """基于关键词的风险检测"""
    if not text:
        return []
    lowered = text.lower()
    labels = []
    for label, words in RISK_KEYWORDS.items():
        for w in words:
            if w.lower() in lowered:
                labels.append(label)
                break
    # 去重并保持顺序
    seen = []
    for label in labels:
        if label not in seen:
            seen.append(label)
    return seen


class SafetyService:
    """检测风险领域并返回标签"""

    async def detect_risk(
        self,
        text: str,
        llm_config: Optional[dict] = None,
        min_confidence: float = 0.6,
    ) -> list[str]:
        """检测文本风险
        
        Args:
            text: 待检测文本
            llm_config: LLM配置（关键词未命中时使用）
            min_confidence: LLM检测的最低置信度
            
        Returns:
            风险标签列表
        """
        # 先尝试关键词快速检测
        keyword_labels = _keyword_detect(text)
        if keyword_labels:
            return keyword_labels
        
        # 关键词未命中，且配置了LLM时，使用LLM检测
        if not llm_config or not text or len(text.strip()) < 6:
            return []

        try:
            llm = build_chat_llm(
                model=llm_config.get("model"),
                api_key=llm_config.get("api_key"),
                api_base_url=llm_config.get("api_base_url"),
                temperature=0.0,
                streaming=False,
            )
            messages = [
                SystemMessage(content=SAFETY_CLASSIFY_PROMPT),
                HumanMessage(content=text.strip()),
            ]
            response = await llm.ainvoke(messages)
            raw = getattr(response, "content", "") or ""
            data = parse_json_obj(raw) or {}
            labels = data.get("labels") or []
            confidence = data.get("confidence")
            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0.0
            if confidence < min_confidence:
                return []
            normalized = []
            for label in labels:
                code = str(label).strip().lower()
                if code in ALLOWED_LABELS and code not in normalized:
                    normalized.append(code)
            return normalized
        except Exception as exc:
            logger.warning(f"Safety classification failed: {exc}")
            return []


# 全局服务实例
safety_service = SafetyService()
