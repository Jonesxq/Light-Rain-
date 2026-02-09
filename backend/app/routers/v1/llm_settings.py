"""User LLM settings routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.llm_settings import llm_settings_crud
from app.models.user import User
from app.schemas.llm_settings import LLMSettingsUpdate, LLMSettingsResponse
from app.utils.crypto import encrypt_text


router = APIRouter(prefix="/llm-settings", tags=["LLM Settings"])


def _normalize_base_url(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        raise HTTPException(status_code=400, detail="api_base_url must start with http:// or https://")
    value = value.rstrip("/")
    if not value.endswith("/v1"):
        value = f"{value}/v1"
    return value


def _mask_key(last4: str | None) -> str | None:
    if not last4:
        return None
    return f"****{last4}"


@router.get("/me", response_model=LLMSettingsResponse)
async def get_my_llm_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings_row = await llm_settings_crud.get_by_user_id(db, current_user.id)
    if not settings_row:
        return LLMSettingsResponse(
            enabled=False,
            api_base_url=None,
            model=None,
            api_key_masked=None,
            has_api_key=False,
            updated_at=None,
        )

    return LLMSettingsResponse(
        enabled=bool(settings_row.enabled),
        api_base_url=settings_row.api_base_url,
        model=settings_row.model,
        api_key_masked=_mask_key(settings_row.api_key_last4),
        has_api_key=bool(settings_row.api_key_encrypted),
        updated_at=settings_row.updated_at,
    )


@router.put("/me", response_model=LLMSettingsResponse)
async def update_my_llm_settings(
    payload: LLMSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)

    if "api_base_url" in update_data:
        update_data["api_base_url"] = _normalize_base_url(update_data.get("api_base_url"))

    if "model" in update_data:
        model_value = (update_data.get("model") or "").strip()
        update_data["model"] = model_value or None

    if "api_key" in update_data:
        api_key_value = update_data.get("api_key")
        if api_key_value is None or str(api_key_value).strip() == "":
            update_data["api_key_encrypted"] = None
            update_data["api_key_last4"] = None
        else:
            api_key_str = str(api_key_value).strip()
            update_data["api_key_encrypted"] = encrypt_text(api_key_str)
            update_data["api_key_last4"] = api_key_str[-4:]
        update_data.pop("api_key", None)

    settings_row = await llm_settings_crud.upsert_for_user(
        db,
        user_id=current_user.id,
        update_data=update_data,
    )

    return LLMSettingsResponse(
        enabled=bool(settings_row.enabled),
        api_base_url=settings_row.api_base_url,
        model=settings_row.model,
        api_key_masked=_mask_key(settings_row.api_key_last4),
        has_api_key=bool(settings_row.api_key_encrypted),
        updated_at=settings_row.updated_at,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_llm_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await llm_settings_crud.delete_for_user(db, current_user.id)
