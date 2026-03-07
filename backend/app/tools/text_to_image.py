"""文生图工具 - 提供文本生成图片功能"""
from http import HTTPStatus
import mimetypes
import os
from urllib.parse import urlparse
import uuid

import requests
from dashscope import ImageSynthesis
from langchain.tools import tool

from app.core.config.settings import settings


def _extract_image_urls(output) -> list[str]:
    """从API响应中提取图片URL列表
    
    Args:
        output: API响应输出对象
        
    Returns:
        list[str]: 图片URL列表
    """
    results = getattr(output, "results", None) or []
    urls: list[str] = []
    for item in results:
        url = None
        if hasattr(item, "url"):
            url = item.url
        elif isinstance(item, dict):
            url = item.get("url")
        if url:
            urls.append(url)
    return urls


def _get_static_root() -> str:
    """获取静态文件根目录路径
    
    Returns:
        str: 静态文件根目录的绝对路径
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))


def _get_image_storage_dir() -> str:
    """获取图片存储目录路径
    
    Returns:
        str: 图片存储目录的绝对路径
    """
    return os.path.join(_get_static_root(), "uploads", "t2i")


def _guess_extension(url: str, content_type: str | None) -> str:
    """根据URL或Content-Type猜测文件扩展名
    
    Args:
        url: 图片URL
        content_type: HTTP响应的Content-Type头
        
    Returns:
        str: 猜测的文件扩展名（包含点号，如.png）
    """
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext
    try:
        path = urlparse(url).path
        _, ext = os.path.splitext(path)
        if ext:
            return ext
    except Exception:
        pass
    return ".png"


def _download_to_static(url: str) -> str:
    """下载图片到静态文件目录并返回相对URL
    
    Args:
        url: 要下载的图片URL
        
    Returns:
        str: 本地静态文件的相对URL（如/static/uploads/t2i/xxx.png）
    """
    storage_dir = _get_image_storage_dir()
    os.makedirs(storage_dir, exist_ok=True)

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    ext = _guess_extension(url, resp.headers.get("Content-Type"))
    filename = f"{uuid.uuid4().hex}{ext}"
    local_path = os.path.join(storage_dir, filename)

    with open(local_path, "wb") as handle:
        handle.write(resp.content)

    static_root = _get_static_root()
    relative_path = os.path.relpath(local_path, static_root).replace(os.sep, "/")
    return f"/static/{relative_path}"


@tool
def text_to_image(prompt: str) -> str:
    """根据文本提示生成图片
    
    使用阿里云通义千问文生图API生成图片，并下载到本地静态目录
    
    Args:
        prompt: 文本提示词，描述要生成的图片内容
        
    Returns:
        str: 生成图片的URL或错误信息
    """
    if not settings.llm.QWEN_API_KEY:
        return "文生图失败：未配置 QWEN_API_KEY"

    cleaned = (prompt or "").strip()
    if not cleaned:
        return "文生图失败：提示词不能为空"

    model_name = getattr(settings.llm, "TEXT_TO_IMAGE_MODEL", None) or "qwen-image-plus"
    size = getattr(settings.llm, "TEXT_TO_IMAGE_SIZE", None) or "1024*1024"

    try:
        rsp = ImageSynthesis.call(
            api_key=settings.llm.QWEN_API_KEY,
            model=model_name,
            prompt=cleaned,
            n=1,
            size=size,
        )
    except Exception as exc:
        return f"文生图失败：{str(exc)}"

    if rsp.status_code != HTTPStatus.OK:
        error_msg = rsp.message or rsp.code or "调用失败"
        return f"文生图失败：{error_msg}"

    urls = _extract_image_urls(rsp.output)
    if not urls:
        return "文生图失败：未返回图片结果"

    saved_urls: list[str] = []
    for url in urls:
        try:
            saved_urls.append(_download_to_static(url))
        except Exception:
            saved_urls.append(url)

    if len(saved_urls) == 1:
        return saved_urls[0]
    return "\n".join(saved_urls)
