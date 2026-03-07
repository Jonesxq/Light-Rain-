"""在线搜索工具 - 提供Google联网搜索功能"""
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain.tools import tool

from app.core.config.settings import settings

# 初始化Google Serper搜索API包装器
search = GoogleSerperAPIWrapper(serper_api_key=settings.llm.SERPER_API_KEY)


@tool
def online_search(query: str) -> str:
    """执行在线搜索查询
    
    使用Google Serper API进行联网搜索，获取最新的网络信息
    
    Args:
        query: 搜索查询字符串
        
    Returns:
        str: 搜索结果摘要
    """
    if not settings.llm.SERPER_API_KEY:
        return "联网搜索失败：未配置 SERPER_API_KEY"
    return search.run(query)
