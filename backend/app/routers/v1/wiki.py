"""Wiki API routes."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.knowledge import kb_crud
from app.crud.wiki import wiki_crud
from app.models.user import User
from app.models.wiki import WikiPage, WikiPatch
from app.services.wiki import wiki_service
from app.services.wiki.service import (
    WikiPatchConflictError,
    WikiPatchNotFoundError,
    WikiPatchUnsupportedOperationError,
)
from app.services.wiki.types import WikiCompileResult

router = APIRouter(prefix="/knowledge/{kb_id}/wiki", tags=["Wiki"])


async def _require_owned_kb(
    db: AsyncSession,
    current_user: User,
    kb_id: int,
) -> None:
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")


def _serialize_page(page: WikiPage) -> dict:
    return {
        "id": page.id,
        "kb_id": page.kb_id,
        "path": page.path,
        "title": page.title,
        "page_type": page.page_type,
        "status": page.status,
        "content_hash": page.content_hash,
        "source_doc_id": page.source_doc_id,
        "provenance": page.provenance,
        "created_at": page.created_at,
        "updated_at": page.updated_at,
    }


def _serialize_patch(patch: WikiPatch) -> dict:
    return {
        "id": patch.id,
        "kb_id": patch.kb_id,
        "page_id": patch.page_id,
        "target_path": patch.target_path,
        "operation": patch.operation,
        "status": patch.status,
        "question": patch.question,
        "answer": patch.answer,
        "patch_markdown": patch.patch_markdown,
        "rationale": patch.rationale,
        "confidence": patch.confidence,
        "provenance": patch.provenance,
        "created_by_message_id": patch.created_by_message_id,
        "created_at": patch.created_at,
        "applied_at": patch.applied_at,
        "rejected_at": patch.rejected_at,
    }


def _serialize_compile_result(result: WikiCompileResult) -> dict:
    return asdict(result)


@router.get("/pages")
async def list_pages(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    pages = await wiki_crud.list_pages(db, kb_id)
    return [_serialize_page(page) for page in pages]


@router.get("/pages/{page_id}")
async def get_page(
    kb_id: int,
    page_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    page = await wiki_crud.get_page(db, kb_id, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")

    try:
        content = wiki_service.storage.read_page(kb_id, page.path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail="Wiki page content not found",
        ) from exc

    return {**_serialize_page(page), "content": content}


@router.get("/search")
async def search_pages(
    kb_id: int,
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    hits = await wiki_service.search_pages(
        db,
        kb_id=kb_id,
        query=q,
        top_k=settings.wiki.WIKI_RETRIEVER_TOP_K,
    )
    return [asdict(hit) for hit in hits]


@router.post("/rebuild")
async def rebuild_wiki(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    documents = await kb_crud.get_completed_documents(db, kb_id)

    results = []
    errors = []
    for doc in documents:
        try:
            result = await wiki_service.compile_document(db, kb_id=kb_id, doc_id=doc.id)
            results.append(_serialize_compile_result(result))
        except Exception as exc:  # Keep rebuilding remaining completed docs.
            errors.append({"doc_id": doc.id, "error": str(exc)})

    return {
        "success": not errors,
        "documents": len(documents),
        "results": results,
        "errors": errors,
    }


@router.post("/lint")
async def lint_wiki(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    pages = await wiki_crud.list_pages(db, kb_id)
    warnings = wiki_service.lint.lint_files(kb_id=kb_id, db_pages=pages)
    return {"warnings": [asdict(warning) for warning in warnings]}


@router.get("/patches")
async def list_patches(
    kb_id: int,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    patches = await wiki_crud.list_patches(db, kb_id, status=status)
    return [_serialize_patch(patch) for patch in patches]


@router.post("/patches/{patch_id}/apply")
async def apply_patch(
    kb_id: int,
    patch_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    try:
        patch = await wiki_service.apply_patch(db, kb_id=kb_id, patch_id=patch_id)
    except WikiPatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Wiki patch not found") from exc
    except WikiPatchConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WikiPatchUnsupportedOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize_patch(patch)


@router.post("/patches/{patch_id}/reject")
async def reject_patch(
    kb_id: int,
    patch_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owned_kb(db, current_user, kb_id)
    try:
        patch = await wiki_service.reject_patch(db, kb_id=kb_id, patch_id=patch_id)
    except WikiPatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Wiki patch not found") from exc
    except WikiPatchConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return _serialize_patch(patch)
