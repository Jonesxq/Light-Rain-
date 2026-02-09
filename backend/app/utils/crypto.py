"""Utility for encrypting/decrypting sensitive text (user LLM API keys)."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config.settings import settings


def _get_fernet() -> Fernet:
    key = getattr(settings.llm, "USER_LLM_KEY_ENCRYPTION_KEY", "") or ""
    if not key:
        raise ValueError("USER_LLM_KEY_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise ValueError("USER_LLM_KEY_ENCRYPTION_KEY is invalid") from exc


def encrypt_text(plain_text: str) -> str:
    if plain_text is None:
        raise ValueError("plain_text is required")
    fernet = _get_fernet()
    token = fernet.encrypt(plain_text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    if not cipher_text:
        raise ValueError("cipher_text is required")
    fernet = _get_fernet()
    try:
        plain = fernet.decrypt(cipher_text.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted token") from exc
    return plain.decode("utf-8")
