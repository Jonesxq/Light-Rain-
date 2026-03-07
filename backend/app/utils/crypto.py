
"""加密工具模块：提供文本加密和解密功能，用于安全存储用户敏感信息（如API密钥）"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config.settings import settings


def _get_fernet() -> Fernet:
    """获取Fernet加密器实例
    
    从配置中读取加密密钥并创建Fernet对象
    
    Returns:
        Fernet: Fernet加密器实例
        
    Raises:
        ValueError: 当USER_LLM_KEY_ENCRYPTION_KEY未配置或无效时
    """
    key = getattr(settings.llm, "USER_LLM_KEY_ENCRYPTION_KEY", "") or ""
    if not key:
        raise ValueError("USER_LLM_KEY_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise ValueError("USER_LLM_KEY_ENCRYPTION_KEY is invalid") from exc


def encrypt_text(plain_text: str) -> str:
    """加密文本
    
    使用Fernet对称加密算法加密明文文本
    
    Args:
        plain_text: 待加密的明文文本
        
    Returns:
        str: 加密后的密文字符串（Base64编码）
        
    Raises:
        ValueError: 当plain_text为None时
    """
    if plain_text is None:
        raise ValueError("plain_text is required")
    fernet = _get_fernet()
    token = fernet.encrypt(plain_text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    """解密文本
    
    使用Fernet对称加密算法解密密文
    
    Args:
        cipher_text: 待解密的密文字符串（Base64编码）
        
    Returns:
        str: 解密后的明文文本
        
    Raises:
        ValueError: 当cipher_text为空或无效时
    """
    if not cipher_text:
        raise ValueError("cipher_text is required")
    fernet = _get_fernet()
    try:
        plain = fernet.decrypt(cipher_text.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted token") from exc
    return plain.decode("utf-8")
