"""获取系统时间工具 - 提供当前日期和时间查询功能"""
from datetime import datetime
from langchain.tools import tool

# 中文星期几名称列表
_WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@tool
def get_system_time() -> str:
    """获取当前系统日期和时间
    
    返回格式化的当前日期、星期和时间信息
    
    Returns:
        str: 包含当前日期、星期和时间的字符串
    """
    now = datetime.now()
    weekday = _WEEKDAY_CN[now.weekday()]
    return (
        f"当前系统日期：{now.strftime('%Y-%m-%d')}（{weekday}），"
        f"当前系统时间：{now.strftime('%H:%M:%S')}"
    )
