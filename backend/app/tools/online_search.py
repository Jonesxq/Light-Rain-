from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain.tools import tool

from app.core.config.settings import settings

search = GoogleSerperAPIWrapper(serper_api_key=settings.llm.SERPER_API_KEY)

@tool
def online_search(query: str) -> str:
    """当你需要回答关于时事的问题时你应该调用此工具，提出有针对性的问题"""
    if not settings.llm.SERPER_API_KEY:
        return "联网搜索失败：未配置 SERPER_API_KEY"
    return search.run(query)


