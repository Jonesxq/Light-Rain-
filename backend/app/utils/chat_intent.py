"""聊天意图识别工具模块：识别用户查询意图（时间、天气等）"""

from __future__ import annotations

import re


def is_time_query(text: str) -> bool:
    """判断文本是否是时间/日期查询
    
    Args:
        text: 用户输入文本
        
    Returns:
        bool: 是时间查询返回True，否则返回False
    """
    if not text:
        return False
    normalized = text.strip()
    # 避免“今天天气”这类问题被误判为时间查询
    weather_keywords = [
        "天气", "气温", "温度", "下雨", "雨", "晴", "阴", "风",
        "空气质量", "AQI", "湿度", "降雨"
    ]
    if any(k in normalized for k in weather_keywords):
        return False

    time_keywords = [
        "时间", "日期", "几点", "几时", "几号", "星期", "周几",
        "现在", "当前", "现在时间", "当前时间", "今天日期", "今日日期"
    ]
    if any(k in normalized for k in time_keywords):
        return True

    # 只出现“今天”时不触发，需搭配“几号/日期/星期”等关键词
    if "今天" in normalized and any(k in normalized for k in ["几号", "几月", "几日", "日期", "星期", "周几"]):
        return True

    return False


def is_weather_query(text: str) -> bool:
    """判断文本是否是天气查询
    
    Args:
        text: 用户输入文本
        
    Returns:
        bool: 是天气查询返回True，否则返回False
    """
    if not text:
        return False
    normalized = text.strip()
    weather_keywords = [
        "天气", "气温", "温度", "下雨", "雨", "晴", "阴", "风",
        "空气质量", "AQI", "湿度", "降雨"
    ]
    return any(k in normalized for k in weather_keywords)


def extract_location(text: str) -> str | None:
    """从天气查询中提取地理位置
    
    Args:
        text: 天气查询文本
        
    Returns:
        str | None: 提取到的地理位置，提取失败返回None
    """
    if not text:
        return None
    normalized = text.strip()
    # 常见格式：'永州天气怎么样' / '北京天气' / '上海今天的天气'
    match = re.search(r"([\u4e00-\u9fffA-Za-z]+?)天气", normalized)
    if match:
        loc = match.group(1).strip()
        # 去掉可能的时间修饰
        for suffix in ["今天", "今日", "现在", "当前", "明天", "后天"]:
            if loc.endswith(suffix):
                loc = loc[: -len(suffix)]
        for prefix in ["今天", "今日", "现在", "当前", "明天", "后天"]:
            if loc.startswith(prefix):
                loc = loc[len(prefix):]
        return loc or None
    return None
