# Wiki Patch Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the human review loop for generated Wiki patches so RAG fallback answers can be approved into the Wiki or rejected without corrupting source pages.

**Architecture:** Keep the current `WikiPatch` table and `/knowledge/{kb_id}/wiki/patches` list endpoint. Add service-level patch application logic that writes Markdown through `WikiStorage`, updates `WikiPage`, records `WikiPageRevision`, refreshes links, then marks the patch `applied` or `rejected`. Add a compact review panel to `Knowledge.vue` for pending patches on the selected knowledge base.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy async sessions, filesystem-backed Markdown Wiki storage, Vue 3, Vite.

---

### Task 1: Backend Patch State Transitions

**Files:**
- Modify: `backend/app/crud/wiki.py`
- Modify: `backend/app/services/wiki/service.py`
- Modify: `backend/app/routers/v1/wiki.py`
- Test: `backend/tests/unit/test_wiki_api.py`

- [ ] Write failing API tests for applying an `append` patch into `faq.md`, rejecting a pending patch, and rejecting non-pending patch transitions.
- [ ] Add `wiki_crud.get_patch()` and `wiki_crud.update_patch_status()`.
- [ ] Add `wiki_service.apply_patch()` to validate pending status, build target Markdown for `append`/`create`, write the page, upsert metadata, create a revision, refresh links, and mark the patch `applied`.
- [ ] Add `wiki_service.reject_patch()` to mark a pending patch `rejected`.
- [ ] Add `POST /knowledge/{kb_id}/wiki/patches/{patch_id}/apply` and `POST /knowledge/{kb_id}/wiki/patches/{patch_id}/reject`.
- [ ] Run `uv run --project backend pytest backend\tests\unit\test_wiki_api.py -q`.

### Task 2: Frontend Review Panel

**Files:**
- Modify: `frontend/src/views/Knowledge.vue`

- [ ] Add state for pending Wiki patches on the active knowledge base.
- [ ] Fetch pending patches when the active knowledge base changes or documents refresh.
- [ ] Render a compact "待写入 Wiki" panel with target path, confidence, question, answer preview, and Markdown preview.
- [ ] Add "采纳" and "拒绝" actions that call the new API endpoints, refresh patches, and show existing center toast feedback.
- [ ] Keep the panel empty state explicit when no knowledge base is selected or there are no pending patches.
- [ ] Run `npm --prefix frontend run build`.

### Task 3: Verification

**Files:**
- Verify only.

- [ ] Run backend focused tests: `uv run --project backend pytest backend\tests\unit\test_wiki_api.py backend\tests\unit\test_chat_wiki_first.py backend\tests\unit\test_wiki_models.py -q`.
- [ ] Run lint on touched backend files: `uv run --project backend ruff check backend\app\crud\wiki.py backend\app\services\wiki\service.py backend\app\routers\v1\wiki.py backend\tests\unit\test_wiki_api.py`.
- [ ] Run frontend build: `npm --prefix frontend run build`.
- [ ] Restart backend and confirm `http://127.0.0.1:8000/health` returns healthy.
