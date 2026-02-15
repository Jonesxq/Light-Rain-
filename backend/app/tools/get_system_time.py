"""tools/get_system_time.py."""
from datetime import datetime
from langchain.tools import tool

_WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@tool
def get_system_time() -> str:
    """get_system_time ???"""
    now = datetime.now()
    weekday = _WEEKDAY_CN[now.weekday()]
    return (
        f"当前系统日期：{now.strftime('%Y-%m-%d')}（{weekday}），"
        f"当前系统时间：{now.strftime('%H:%M:%S')}"
    )
