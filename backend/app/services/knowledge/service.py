"""知识库能力门面服务：统一聚合检索、入库、存储与运行时组件。"""

from __future__ import annotations

from app.services.knowledge.ingest import KnowledgeIngest
from app.services.knowledge.retrieval import KnowledgeRetrieval
from app.services.knowledge.runtime import KnowledgeRuntime
from app.services.knowledge.storage import KnowledgeStorage


class KnowledgeService:
    """知识库领域门面：对外暴露统一接口，对内委托给分域组件。"""

    def __init__(self):
        """初始化知识库子组件并完成运行时依赖准备。"""
        self._runtime = KnowledgeRuntime(self)
        self._storage = KnowledgeStorage(self)
        self._retrieval = KnowledgeRetrieval(self)
        self._ingest = KnowledgeIngest(self)
        self._ops = (self._runtime, self._storage, self._retrieval, self._ingest)
        self._runtime.init_components()

    def __getattr__(self, name: str):
        """将未知属性按顺序代理到各子组件，保持旧调用方式兼容。"""
        for component in self._ops:
            if hasattr(component, name):
                return getattr(component, name)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name}")
