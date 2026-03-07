"""天气查询工具 - 提供全球天气信息查询功能"""
from langchain.tools import tool
import re
import requests

from app.core.config.settings import settings

# 中文字符正则表达式
_CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def _looks_chinese(text: str) -> bool:
    """判断文本是否包含中文字符
    
    Args:
        text: 待检查的文本
        
    Returns:
        bool: 包含中文字符返回True，否则返回False
    """
    return bool(_CHINESE_CHAR_RE.search(text or ""))


def _resolve_location(query: str) -> str:
    """解析位置查询，优化天气API的查询精度
    
    对于中文地点，会尝试匹配中国/中国大陆地区，提高查询准确率
    
    Args:
        query: 位置查询字符串
        
    Returns:
        str: 解析后的位置查询字符串
    """
    # 未配置密钥时直接返回原查询
    if not settings.llm.WEATHER_API_KEY:
        return query

    try:
        search_url = "http://api.weatherapi.com/v1/search.json"
        resp = requests.get(
            search_url,
            params={"key": settings.llm.WEATHER_API_KEY, "q": query},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json() or []

        if not results:
            return query

        # 优先匹配中国/中国大陆/中文地区
        if _looks_chinese(query):
            for item in results:
                country = (item.get("country") or "").lower()
                if "china" in country or "中国" in item.get("country", ""):
                    # 组合出更明确的查询，提升命中精度
                    name = item.get("name") or query
                    region = item.get("region") or ""
                    if region:
                        return f"{name}, {region}, China"
                    return f"{name}, China"

        # 若无法识别中国结果，则选第一个
        first = results[0]
        name = first.get("name") or query
        region = first.get("region") or ""
        country = first.get("country") or ""
        if region or country:
            return ", ".join([p for p in [name, region, country] if p])
        return query

    except Exception:
        # 兜底：任何异常都不影响主流程
        return query


@tool
def get_weather(location: str) -> str:
    """查询指定位置的天气信息
    
    使用WeatherAPI查询天气，支持全球城市查询，对中文地点有特殊优化
    
    Args:
        location: 要查询天气的位置（城市名、地区名等）
        
    Returns:
        str: 格式化的天气信息，包含温度、湿度、风向、空气质量等
    """
    # 对地点做一次消歧，避免命中错误的城市/国家
    resolved_location = _resolve_location(location)

    # 当前天气接口（开启空气质量）
    url = "http://api.weatherapi.com/v1/current.json"
    params = {
        "key": settings.llm.WEATHER_API_KEY,
        "q": resolved_location,
        "lang": "zh",
        "aqi": "yes"
    }

    try:
        if not settings.llm.WEATHER_API_KEY:
            return "天气查询失败：未配置 WEATHER_API_KEY"
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        location_name = data["location"]["name"]
        region = data["location"].get("region", "")
        country = data["location"].get("country", "")
        localtime = data["location"].get("localtime", "")
        condition = data["current"]["condition"]["text"]
        temp_c = data["current"]["temp_c"]
        feelslike_c = data["current"]["feelslike_c"]
        humidity = data["current"]["humidity"]
        wind_kph = data["current"].get("wind_kph")
        wind_dir = data["current"].get("wind_dir")
        uv = data["current"].get("uv")
        air_quality = data["current"].get("air_quality") or {}
        pm25 = air_quality.get("pm2_5")
        aqi_cn = air_quality.get("gb-defra-index")

        # 组装更工整的返回格式
        region_text = f"{region}" if region else ""
        place_text = "，".join([p for p in [location_name, region_text, country] if p])
        header = f"✅ 我已为你实时查询{place_text}今天的最新天气："
        if localtime:
            date_part = localtime.split(" ")[0]
            header = f"✅ 我已为你实时查询{place_text}今日（{date_part}）的最新天气："

        lines = [
            header,
            f"🌤 {place_text}当前天气",
            f"- 天气状况：{condition}",
            f"- 气温：{temp_c}℃（体感 {feelslike_c}℃）",
            f"- 湿度：{humidity}%",
        ]

        # 如果用户是中文地点但返回的国家不是中国，给出轻提示
        if _looks_chinese(location) and country and "china" not in country.lower() and "中国" not in country:
            lines.append(f"- 提示：当前返回的地区属于 {country}，如需更精确可尝试\"{location}，中国/省份\"")

        if wind_kph is not None:
            wind_text = f"{wind_kph} km/h"
            if wind_dir:
                wind_text = f"{wind_dir}风 {wind_text}"
            lines.append(f"- 风向风力：{wind_text}")

        if uv is not None:
            lines.append(f"- 紫外线指数：{uv}")

        if pm25 is not None or aqi_cn is not None:
            aq_parts = []
            if pm25 is not None:
                aq_parts.append(f"PM2.5≈{round(pm25, 1)}")
            if aqi_cn is not None:
                aq_parts.append(f"AQI指数≈{aqi_cn}")
            lines.append(f"- 空气质量：{'，'.join(aq_parts)}")

        return "\n".join(lines)

    except Exception as e:
        return f"天气查询失败，原因：{str(e)}"
