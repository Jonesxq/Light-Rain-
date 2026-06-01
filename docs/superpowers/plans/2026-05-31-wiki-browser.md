# Wiki Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visible Wiki browser to the knowledge-base page so users can inspect the Markdown Wiki maintained by uploads, RAG fallback answers, and approved model suggestions.

**Architecture:** Reuse the existing Wiki API: `GET /knowledge/{kb_id}/wiki/pages` for page metadata and `GET /knowledge/{kb_id}/wiki/pages/{page_id}` for Markdown content. Extend `frontend/src/views/Knowledge.vue` with Wiki page state, a page list, and a read-only Markdown preview. Refresh Wiki pages whenever the active knowledge base changes and after a Wiki patch is accepted.

**Tech Stack:** Vue 3 Composition API, existing `apiFetch`, existing FastAPI Wiki routes, Vite build verification.

---

### Task 1: Wiki Browser State

**Files:**
- Modify: `frontend/src/views/Knowledge.vue`

- [ ] Add `wikiPages`, `selectedWikiPage`, and `wikiPageContent` state to track page metadata, selected page, loading status, and fetched Markdown.
- [ ] Add `fetchWikiPages()` that calls `/knowledge/${activeKb.value.id}/wiki/pages`, sorts pages by type and path, and preserves the selected page where possible.
- [ ] Add `selectWikiPage(page)` that calls `/knowledge/${activeKb.value.id}/wiki/pages/${page.id}` and stores the returned page with `content`.
- [ ] Clear Wiki state when no knowledge base is selected or the active knowledge base is deleted.

### Task 2: Wiki Browser UI

**Files:**
- Modify: `frontend/src/views/Knowledge.vue`

- [ ] Add a `知识库 Wiki` panel below the existing panels.
- [ ] Render a page list with type labels, page titles, paths, and update times.
- [ ] Render a read-only Markdown preview for the selected page.
- [ ] Provide clear empty states for no active knowledge base, no Wiki pages, and no selected page.
- [ ] Refresh Wiki pages after accepting a pending Wiki patch.

### Task 3: Verification

**Files:**
- Verify only.

- [ ] Run `npm --prefix frontend run build`.
- [ ] Run focused backend Wiki tests if backend files change.
- [ ] Confirm backend health after any restart with `Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -Method Get`.
