# Wiki-First RAG Design

Date: 2026-05-29

Status: Approved design direction, pending user review of this written spec.

Reference: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

## Overview

This design evolves the current knowledge-base RAG system into a wiki-first knowledge system inspired by Karpathy's LLM-maintained wiki pattern.

The current project already has a strong raw retrieval layer:

- Uploaded source files are parsed, chunked, summarized, and stored.
- Raw chunks are preserved in sidecar `.chunks.jsonl` files.
- Chunk summaries are stored in MySQL and embedded into Milvus.
- Retrieval uses query rewrite, BM25, semantic search, RRF fusion, reranking, and source metadata.

The new system keeps that layer intact and adds a persistent Markdown wiki layer above it. The wiki becomes the first knowledge surface used to answer questions. Raw RAG remains the fallback when the wiki cannot answer. High-quality fallback answers are converted into pending wiki patches so the system compounds knowledge over time.

The central answering rule is:

1. Try to answer from the wiki first.
2. If the wiki cannot answer with enough confidence, fall back to raw RAG.
3. If raw RAG produces a useful, source-backed answer, create a pending wiki patch.

This keeps the system reliable while making it progressively more useful.

## Goals

- Add a persistent wiki layer per knowledge base.
- Let the wiki answer user questions before raw RAG is used.
- Preserve the existing raw RAG path as a reliable fallback.
- Write high-quality raw RAG answers back into the wiki through reviewable patches.
- Make all wiki content traceable to raw source chunks, chat messages, or explicit user confirmation.
- Make `schema.md`, `index.md`, and `log.md` first-class wiki control files, not incidental generated pages.
- Use cross-links, frontmatter, and parseable log entries so the wiki remains useful outside the app as plain Markdown.
- Provide a basic frontend workspace for browsing wiki pages, reviewing patches, and running lint checks.
- Keep the first implementation incremental and reversible.

## Non-Goals

- Replace Milvus, BM25, sidecar files, or existing knowledge ingestion.
- Automatically rewrite large parts of the wiki without review.
- Build a full Markdown editor in the first version.
- Guarantee perfect entity/topic extraction in the first version.
- Make the wiki the only source of truth. Raw sources remain the factual base layer.

## Design Principles

### Wiki-First

If the wiki can answer a question with enough confidence and cited wiki pages, the system returns that answer directly without running raw RAG. This makes the wiki a real long-term knowledge layer rather than an extra context blob appended to every prompt.

### Raw RAG Fallback

When the wiki cannot answer, the existing RAG pipeline retrieves raw chunks and generates the answer. This preserves current behavior and avoids regressions while the wiki is sparse or stale.

### Answer Compounding

When fallback RAG answers a useful, source-backed question, the system creates a pending wiki patch. Once applied, future similar questions can be answered by the wiki layer.

### Source Provenance

Every automatically generated wiki addition must include provenance. Provenance can reference:

- `doc_id`
- `chunk_id`
- `chunk_index`
- `message_id`
- source page paths
- user confirmation events

### Conservative Automation

The first version uses manual patch review by default. Low-risk automatic writes can be enabled later through configuration.

### Rebuildability

Auto-generated source pages should be rebuildable from raw source chunks. The wiki can contain user-curated knowledge, but generated source summaries must not be the only copy of factual information.

### Markdown Portability

The wiki must remain a usable directory of Markdown files even without the web app. Database rows index and audit the wiki, but the Markdown files carry enough frontmatter, links, provenance, and log history to be inspected in tools such as Obsidian or a normal code editor.

### Index-First Navigation

Following the LLM Wiki pattern, query-time wiki retrieval starts from `index.md`. The index is the content map of the wiki, and the retriever uses it as the first navigation spine before scanning all pages.

### Parseable History

`log.md` is append-only and uses a consistent heading format so both humans and simple tools can inspect wiki history.

## Architecture

The system has three layers.

```text
Raw Sources Layer
  Uploaded files
  sidecar raw chunks
  kb_doc_chunks summaries
  Milvus vectors
  structured source metadata

Wiki Layer
  Markdown pages
  page index rows
  page revision rows
  pending patches
  lint reports

Operations Layer
  schema.md rules
  compile_document
  wiki_answer
  raw_rag_fallback
  writeback_patch
  apply_patch
  reject_patch
  rebuild
  lint
  maintenance commands
```

Existing knowledge ingestion continues to populate the Raw Sources Layer. New wiki services compile, query, lint, and patch the Wiki Layer.

`schema.md` is part of the Operations Layer. It is the operational contract for LLM maintainers, compilers, retrievers, lint jobs, and writeback patch generation.

## Main Data Flows

### Document Ingestion

Current flow remains:

```text
Upload file
-> parse and chunk
-> summarize chunks
-> write raw chunks to sidecar
-> write summary vectors to Milvus
-> write chunk metadata to MySQL
-> mark document completed
```

New wiki flow starts after completion:

```text
Document completed
-> load schema.md maintenance rules
-> WikiCompiler reads raw chunks, chunk summaries, and structured metadata
-> create or update sources/{doc_id}-{slug}.md
-> update index.md
-> append log.md
-> create pending cross-reference patches for candidate topics/entities/links
-> record wiki_pages rows
-> record wiki_page_revisions rows
-> extract wiki links for graph and lint
-> run lightweight lint
```

The first version guarantees source pages, index, and log. It also generates pending cross-reference patches for topic pages, entity pages, and related-page links when the source clearly suggests them. This keeps initial automation safe while still following the LLM Wiki pattern that a single source can affect multiple wiki pages.

Ingest can run in three modes:

```text
auto
pending_review
assisted
```

`auto` compiles source pages immediately. `pending_review` stores generated source pages as patches. `assisted` lets the user review the generated source summary, important terms, and proposed cross-links before applying them. The default is `auto` for compatibility, but `assisted` is the closest mode to the original LLM Wiki workflow.

### Question Answering

```text
User question
-> save user message
-> rewrite / normalize query as needed
-> WikiRetriever reads index.md to identify candidate wiki paths
-> WikiRetriever ranks index candidates plus all active pages
-> WikiAnswerer attempts wiki-only answer
-> if answer is good enough: return wiki answer
-> otherwise: run existing raw RAG retrieval and answer
-> if raw RAG answer is useful: create pending wiki patch
-> save assistant message and debug snapshot
```

The answer result records whether it came from the wiki or raw RAG.

### Writeback

```text
Raw RAG answer
-> WritebackEvaluator checks if the answer is reusable and source-backed
-> WikiWriteback generates a patch proposal
-> patch is stored as pending
-> user reviews patch in frontend
-> applying patch atomically updates Markdown and records a revision
```

The default writeback mode is manual.

## Backend Modules

Add a new package:

```text
backend/app/services/wiki/
  __init__.py
  service.py
  storage.py
  compiler.py
  retriever.py
  answerer.py
  fallback.py
  writeback.py
  patcher.py
  lint.py
  links.py
  maintenance.py
  prompts.py
  types.py
```

### `WikiService`

Facade used by routers and chat flows.

Responsibilities:

- Own subcomponents.
- Provide stable public methods.
- Keep wiki internals out of `rag_flow.py`.

Main methods:

```python
async def compile_document(db, kb_id: int, doc_id: int) -> WikiRunResult: ...
async def rebuild_kb(db, user_id: int, kb_id: int) -> WikiRunResult: ...
async def lint_kb(db, user_id: int, kb_id: int) -> WikiLintResult: ...
async def answer_with_fallback(db, user_id: int, kb_id: int, question: str, model: str | None, session_id: int) -> WikiAnswerResult: ...
async def list_pages(db, user_id: int, kb_id: int) -> list[WikiPageSummary]: ...
async def get_page(db, user_id: int, kb_id: int, page_id: int) -> WikiPageDetail: ...
async def list_patches(db, user_id: int, kb_id: int) -> list[WikiPatchSummary]: ...
async def apply_patch(db, user_id: int, kb_id: int, patch_id: int) -> WikiPatchResult: ...
async def reject_patch(db, user_id: int, kb_id: int, patch_id: int) -> WikiPatchResult: ...
async def search_pages(db, user_id: int, kb_id: int, query: str) -> WikiSearchResult: ...
```

### `WikiStorage`

Handles safe Markdown file operations.

Responsibilities:

- Resolve knowledge-base wiki root.
- Validate page paths.
- Reject path traversal such as `../`.
- Read pages.
- Write pages atomically through a temporary file and replace.
- Compute content hashes.
- Create directories as needed.

Wiki root:

```text
backend/storage/wiki/kb_{kb_id}/
```

### `WikiCompiler`

Builds wiki pages from raw knowledge documents.

Responsibilities:

- Read document metadata from MySQL.
- Read raw chunks from sidecar.
- Read chunk summaries from `kb_doc_chunks`.
- Generate source page Markdown.
- Update `index.md`.
- Append `log.md`.
- Generate candidate cross-reference patches for topics, entities, and related pages.
- Create or update `wiki_pages` rows.
- Record `wiki_page_revisions`.

First-version compiler outputs:

- `schema.md`
- `index.md`
- `log.md`
- `sources/{doc_id}-{slug}.md`
- updates to `open_questions.md` only when the compiler finds obvious missing or ambiguous source metadata

Cross-reference patch outputs:

- candidate `topics/{slug}.md` pages
- candidate `entities/{slug}.md` pages
- candidate links from source pages to topics/entities
- candidate additions to `open_questions.md`

These are pending patches unless the ingest mode explicitly allows low-risk automatic application.

### `WikiRetriever`

Finds relevant wiki pages for a user question.

First-version retrieval:

1. Read `index.md`.
2. Extract linked page paths and section headings from the index.
3. Rank index-linked candidates against the user query.
4. Load active wiki pages from `wiki_pages`.
5. Run BM25 over page title, path, page type, frontmatter, and Markdown content.
6. Merge index candidates and BM25 candidates.
7. Return top pages with snippets.

The retriever should prefer pages reachable from `index.md` when scores are similar. This keeps the wiki navigational rather than just a pile of Markdown chunks.

Future optional retrieval:

- Embed wiki pages into a separate Milvus collection or namespace.
- Fuse wiki BM25 and wiki semantic retrieval.

### `WikiLinks`

Extracts and indexes links between wiki pages.

Responsibilities:

- Parse Markdown links and wiki-style links.
- Extract provenance links such as `[source:doc=12 chunk=34]`.
- Store page-to-page links in `wiki_links`.
- Provide backlink information for page detail views.
- Support lint checks for missing, orphan, stale, or suspicious links.

Link types:

```text
related_to
cites
defines
answers
contradicts
supersedes
mentions
```

### `WikiMaintenance`

Optional scriptable command layer for local maintenance and debugging.

Commands:

```text
wiki rebuild {kb_id}
wiki lint {kb_id}
wiki search {kb_id} "{query}"
wiki apply-patch {kb_id} {patch_id}
wiki reject-patch {kb_id} {patch_id}
```

These commands can be implemented as internal Python scripts first. A public CLI or MCP server is a later extension.

### `WikiAnswerer`

Attempts a wiki-only answer.

It must ask the LLM to answer only from wiki page content and output structured JSON:

```json
{
  "can_answer": true,
  "confidence": 0.82,
  "answer": "answer text",
  "missing_reason": "",
  "used_pages": [
    {
      "path": "sources/12-api-doc.md",
      "title": "API Doc"
    }
  ]
}
```

Server-side acceptance rules:

```text
can_answer == true
confidence >= WIKI_ANSWER_CONFIDENCE_THRESHOLD
answer is not empty
used_pages is not empty
```

Default threshold:

```text
WIKI_ANSWER_CONFIDENCE_THRESHOLD=0.72
```

If validation fails, the system falls back to raw RAG.

### `WikiFallback`

Coordinates the two-stage answer path.

Responsibilities:

- Try wiki answer first.
- Call existing `kb_service.search_knowledge()` only when wiki answer fails.
- Build the raw RAG prompt using existing behavior.
- Save enough metadata for prompt snapshots.
- Trigger writeback patch creation after successful raw RAG answers.

This component prevents `ChatRagFlow` from becoming a large mixed wiki/RAG implementation.

### `WikiWriteback`

Evaluates raw RAG answers and creates pending patches.

Writeback eligibility:

- Raw RAG returned at least one source.
- Answer does not say the knowledge base lacks relevant records.
- Question is not casual chat, formatting-only, simple translation, or a temporary tool request.
- Answer contains reusable knowledge such as definitions, procedures, comparisons, decisions, FAQ entries, project facts, constraints, or entity descriptions.
- Patch provenance includes raw source references.

Patch target rules:

```text
common reusable Q&A -> faq.md append
clear topic -> topics/{slug}.md append or create
information gap -> open_questions.md append
source conflict -> contradictions.md append
document-level summary -> sources/{doc_id}-{slug}.md section update
```

Default behavior:

```text
Create pending patch, do not apply automatically.
```

### `WikiPatcher`

Applies or rejects patches.

Apply behavior:

- Validate ownership.
- Validate patch status is pending.
- Validate target path.
- Read current page.
- Apply create, append, or replace-section operation.
- Write atomically.
- Update or create `wiki_pages`.
- Insert `wiki_page_revisions`.
- Mark patch applied.
- Append `log.md`.

Reject behavior:

- Validate ownership.
- Mark patch rejected.
- Preserve patch record for audit.

### `WikiLint`

Runs consistency checks.

First-version checks:

- Page path exists for every active `wiki_pages` row.
- Markdown file has a matching `wiki_pages` row.
- Generated source pages have provenance.
- Source pages linked to missing documents are stale.
- Pending patches point to valid target paths.
- Pages without inbound links are reported as possible orphan pages.
- Pages with automatic content but no source references are reported.
- `index.md` links point to existing pages.
- Required frontmatter is present and parseable.
- `log.md` entries use the required heading format.

Future checks:

- Topic/entity conflicts.
- Duplicate pages.
- Broken cross-links.
- Contradictory claims.
- Stale pages after document reindex.
- Weakly connected topic/entity pages.
- Missing backlinks from source pages to derived topic/entity pages.

## Database Models

### `wiki_pages`

Indexes Markdown pages and connects file content to permissions, status, search, and frontend display.

Fields:

```text
id
kb_id
path
title
page_type
status
content_hash
source_doc_id nullable
provenance JSON
created_at
updated_at
```

`page_type` values:

```text
index
schema
log
source
topic
entity
faq
open_questions
contradictions
patch
```

`status` values:

```text
active
stale
failed
deleted
```

Indexes:

```text
kb_id
(kb_id, path) unique
(kb_id, page_type)
(kb_id, status)
source_doc_id
```

### `wiki_page_revisions`

Stores page snapshots for rollback and audit.

Fields:

```text
id
page_id
kb_id
path
content_hash
content_snapshot
change_reason
provenance JSON
created_at
```

`change_reason` values:

```text
ingest
writeback
manual_patch
rebuild
lint_fix
system
```

### `wiki_patches`

Stores pending, applied, and rejected writeback proposals.

Fields:

```text
id
kb_id
page_id nullable
target_path
operation
status
question
answer
patch_markdown
rationale
confidence
provenance JSON
created_by_message_id nullable
created_at
applied_at nullable
rejected_at nullable
```

`operation` values:

```text
create
append
replace_section
```

`status` values:

```text
pending
applied
rejected
failed
```

### `wiki_links`

Indexes links and backlinks between wiki pages.

Fields:

```text
id
kb_id
from_page_id
from_path
to_page_id nullable
to_path
link_type
anchor_text nullable
provenance JSON
created_at
```

Indexes:

```text
kb_id
(kb_id, from_path)
(kb_id, to_path)
(kb_id, link_type)
```

The link table is derived from Markdown files and can be rebuilt. It exists to support graph views, backlinks, lint, and index-first retrieval.

### `wiki_runs`

Tracks compile, rebuild, lint, and writeback jobs.

Fields:

```text
id
kb_id
doc_id nullable
run_type
status
metrics JSON
error_msg nullable
created_at
finished_at nullable
```

`run_type` values:

```text
ingest_doc
rebuild_kb
lint
writeback
patch_apply
```

`status` values:

```text
running
succeeded
failed
```

## Markdown File Structure

Each knowledge base gets a directory:

```text
backend/storage/wiki/kb_{kb_id}/
  schema.md
  index.md
  log.md
  open_questions.md
  contradictions.md
  faq.md
  assets/
  sources/
    12-product-spec.md
    13-api-doc.md
  topics/
    retrieval.md
    deployment.md
  entities/
    milvus.md
    qwen.md
  patches/
    2026-05-29-message-456.patch.md
```

All content pages should include YAML frontmatter. Frontmatter keeps Markdown portable and gives non-app tools enough structure to query or inspect pages.

Common frontmatter:

```yaml
---
title: API Doc
page_type: source
status: active
created_at: 2026-05-29T14:20:00
updated_at: 2026-05-29T14:40:00
tags: [source, api]
source_count: 8
---
```

Source pages merge source-specific metadata into the same frontmatter block:

```yaml
---
title: API Doc
page_type: source
status: active
doc_id: 12
file_name: api-doc.md
file_type: .md
chunk_count: 18
created_at: 2026-05-29T14:20:00
updated_at: 2026-05-29T14:40:00
tags: [source, api]
source_count: 8
---
```

### `schema.md`

Maintenance rules for the wiki.

It describes:

- Page types.
- Allowed write operations.
- Required provenance format.
- Citation format.
- Rules against unsupported claims.
- Section names used by generated pages.
- Manual review policy.
- Required frontmatter keys.
- Required log entry format.
- Ingest workflow.
- Query workflow.
- Lint workflow.
- Writeback workflow.
- Patch review workflow.
- Do-not-overwrite rules for human-authored sections.

Required operations in `schema.md`:

```text
ingest(source)
  read raw source metadata and chunks
  summarize source
  update source page
  update index.md
  append log.md
  propose topic/entity/link patches
  run lint

query(question)
  read index.md
  retrieve candidate wiki pages
  answer only if wiki support is sufficient
  otherwise declare wiki miss

writeback(question, answer, raw_sources)
  decide whether the answer is reusable
  choose target page
  create pending patch with provenance
  append log.md

lint()
  check provenance
  check frontmatter
  check index links
  check backlinks
  check stale pages
  check contradictions
```

This file is the operational contract for every LLM call that writes or interprets wiki content.

### `index.md`

Knowledge-base landing page.

`index.md` is the first file read by wiki query. It must remain concise, navigable, and link-rich. The index should not become a full summary of every page; it should help the retriever choose which pages to read next.

Sections:

```text
# Index

## Overview

## Main Topics

## Entities

## Source Documents

## Recent Updates

## Open Questions
```

Index entries should use normal Markdown links:

```md
- [API Doc](sources/12-api-doc.md) - REST endpoint details and auth behavior.
- [Retrieval](topics/retrieval.md) - BM25, vector search, rerank, and source handling.
```

### `log.md`

Chronological wiki activity.

Log entries use a parseable heading:

```md
## [2026-05-29 14:20] ingest | doc_id=12 | API Doc
## [2026-05-29 14:31] query | message_id=456 | wiki_miss -> raw_rag
## [2026-05-29 14:33] patch_created | patch_id=123 | target=faq.md
## [2026-05-29 14:37] patch_applied | patch_id=123 | target=faq.md
## [2026-05-29 14:40] lint | warnings=3
```

Entries include:

- document compiled
- page created
- page updated
- patch created
- patch applied
- lint warning
- rebuild completed

`log.md` is append-only except for explicit repair operations that preserve the old content in a page revision.

### `sources/*.md`

One page per raw document.

Suggested structure:

```text
# {Document Title}

## Source Metadata

- doc_id:
- file_name:
- file_type:
- chunk_count:
- created_at:

## Summary

## Key Points

## Important Terms

## Questions This Source Can Answer

## Source References

- [source:doc=12 chunk=34]
- [source:doc=12 chunk_index=5]

## Related Pages
```

Related pages should be explicit links to topics, entities, FAQ entries, or open questions. These links feed `wiki_links` and graph/lint views.

### `assets/`

Stores extracted or uploaded non-text assets related to wiki pages.

Examples:

```text
assets/doc-12-diagram-1.png
assets/doc-20-table-export.csv
```

Asset references must include provenance in the referencing page. First-version support can be limited to storing and linking assets; image understanding and chart generation are later extensions.

### `faq.md`

Stores reviewed reusable Q&A generated from fallback answers.

Suggested entry:

```text
## {Question}

{Answer}

Provenance:
- [source:doc=12 chunk=34]
- [message:456]
```

### `topics/*.md`

Topic pages are grown from reviewed patches and later compiler passes.

Suggested structure:

```text
# {Topic}

## Summary

## Key Facts

## Procedures

## Decisions

## Related Sources

## Related Questions
```

### `entities/*.md`

Entity pages for products, systems, people, APIs, models, or organizations.

Suggested structure:

```text
# {Entity}

## What It Is

## Properties

## Relationships

## Source Mentions

## Related Pages
```

### `open_questions.md`

Tracks questions the wiki or source layer cannot answer confidently.

### `contradictions.md`

Tracks possible conflicts between sources or between generated wiki content and source facts.

## Provenance Format

Use stable inline provenance markers:

```text
[source:doc=12 chunk=34]
[source:doc=12 chunk_index=5]
[message:456]
[wiki:sources/12-product-spec.md]
```

Frontend can resolve source markers through existing chunk preview endpoints when `doc_id` and `chunk_id` or `chunk_index` are present.

## Chat Integration

The current `ChatRagFlow` should call `wiki_service.answer_with_fallback()` when wiki RAG is enabled.

Configuration:

```text
WIKI_RAG_ENABLED=true
WIKI_WRITEBACK_MODE=manual
```

Expected result shape:

```json
{
  "answer_mode": "wiki",
  "content": "...",
  "confidence": 0.82,
  "sources": [],
  "wiki_sources": [],
  "raw_sources": [],
  "writeback_patch_id": null,
  "wiki_missing_reason": ""
}
```

`answer_mode` values:

```text
wiki
raw_rag
raw_rag_no_writeback
error
```

The assistant message should store:

- answer text
- model name
- token count
- existing `sources`
- wiki sources in prompt snapshot payload
- raw sources in prompt snapshot payload
- answer mode
- writeback patch ID if created

The first version can keep the existing `chat_messages.sources` field compatible by storing displayable source dictionaries and putting detailed wiki/raw separation in `ChatPromptSnapshot.payload`.

## API Design

Add a router under the existing knowledge API.

```text
GET    /api/v1/knowledge/{kb_id}/wiki/pages
GET    /api/v1/knowledge/{kb_id}/wiki/pages/{page_id}
POST   /api/v1/knowledge/{kb_id}/wiki/rebuild
POST   /api/v1/knowledge/{kb_id}/wiki/lint
GET    /api/v1/knowledge/{kb_id}/wiki/patches
POST   /api/v1/knowledge/{kb_id}/wiki/patches/{patch_id}/apply
POST   /api/v1/knowledge/{kb_id}/wiki/patches/{patch_id}/reject
```

All endpoints must verify that the current user owns the knowledge base.

### List Pages

Returns page tree data:

```json
[
  {
    "id": 1,
    "path": "index.md",
    "title": "Index",
    "page_type": "index",
    "status": "active",
    "updated_at": "2026-05-29T00:00:00"
  }
]
```

### Get Page

Returns Markdown content and metadata:

```json
{
  "id": 1,
  "path": "sources/12-api-doc.md",
  "title": "API Doc",
  "page_type": "source",
  "status": "active",
  "content": "# API Doc\n...",
  "provenance": {}
}
```

### List Patches

Returns pending and historical patches:

```json
[
  {
    "id": 123,
    "target_path": "faq.md",
    "operation": "append",
    "status": "pending",
    "question": "...",
    "confidence": 0.84,
    "created_at": "2026-05-29T00:00:00"
  }
]
```

### Apply Patch

Applies one pending patch and returns the updated patch status.

### Reject Patch

Marks one pending patch as rejected.

## Frontend Design

Extend `frontend/src/views/Knowledge.vue` with a workspace for the selected knowledge base.

Top-level tabs:

```text
知识库文件 | Wiki | Patches | Lint
```

### Wiki Tab

Layout:

- Left: page tree grouped by page type.
- Right: Markdown preview.
- Top actions: Rebuild, Lint, refresh.

First version displays Markdown as readable text/HTML. It does not need a full editor.

### Patches Tab

Shows pending patches.

Each patch displays:

- source question
- target page
- operation
- confidence
- provenance summary
- proposed Markdown

Actions:

- Apply
- Reject
- Refresh

### Lint Tab

Shows lint warnings:

- missing page file
- stale source page
- missing source provenance
- orphan page
- invalid pending patch target

## Configuration

Add wiki config module:

```text
WIKI_RAG_ENABLED=true
WIKI_WRITEBACK_MODE=manual
WIKI_INGEST_MODE=auto
WIKI_ANSWER_CONFIDENCE_THRESHOLD=0.72
WIKI_RETRIEVER_TOP_K=5
WIKI_STORAGE_DIR=storage/wiki
WIKI_MAX_PAGE_CHARS=12000
WIKI_PATCH_CONFIDENCE_THRESHOLD=0.70
WIKI_AUTO_COMPILE_ON_INGEST=true
```

`WIKI_WRITEBACK_MODE` values:

```text
manual
auto_low_risk
disabled
```

`WIKI_INGEST_MODE` values:

```text
auto
pending_review
assisted
```

First version default:

```text
manual
```

The default ingest mode is:

```text
auto
```

Operators who want the closest LLM Wiki workflow can switch to `assisted`.

## Error Handling

### Wiki Compilation Failure

If wiki compilation fails after document ingestion:

- keep document status completed
- record `wiki_runs` failure
- log warning/error
- existing RAG remains usable

### Wiki Retrieval Failure

If wiki retrieval fails:

- skip wiki answer
- run raw RAG fallback
- include failure detail in prompt snapshot

### Wiki Answer Invalid JSON

If the LLM returns invalid JSON:

- treat wiki answer as unavailable
- run raw RAG fallback
- record missing reason as `invalid_wiki_answer_payload`

### Raw RAG Failure

If raw RAG also fails:

- return an appropriate error using current chat error handling
- do not create a patch

### Patch Generation Failure

If patch generation fails:

- return raw RAG answer to the user
- record writeback failure in `wiki_runs`
- do not interrupt chat response

### Patch Apply Failure

If applying a patch fails:

- leave patch pending or mark failed depending on failure point
- do not partially write Markdown
- record error message

## Security and Data Safety

- Wiki page paths must be relative and normalized.
- Paths containing `..`, drive letters, absolute prefixes, or backslashes after normalization are rejected.
- All wiki endpoints check knowledge-base ownership.
- Markdown writes use atomic replace.
- Page revisions preserve previous content before changes.
- Raw sources remain unchanged.
- Automatically generated wiki content must include provenance.
- Pending patches are not applied until approved in manual mode.
- Human-authored sections marked by schema rules must not be overwritten by automatic rebuilds.
- Derived tables such as `wiki_links` can be rebuilt from Markdown and must not be treated as the only source of truth.

## Testing Strategy

### Unit Tests

- `WikiStorage` rejects path traversal.
- `WikiStorage` writes pages atomically.
- `WikiCompiler` creates source page, index, log, and page rows from fake chunks.
- `WikiCompiler` creates pending cross-reference patches for clear topic/entity candidates.
- `WikiRetriever` ranks relevant pages above unrelated pages.
- `WikiRetriever` prefers index-linked pages when scores are close.
- `WikiAnswerer` rejects low-confidence answers.
- `WikiAnswerer` rejects answers with no used pages.
- `WikiFallback` calls raw RAG when wiki answer fails validation.
- `WikiWriteback` skips non-reusable answers.
- `WikiWriteback` creates pending patch for source-backed reusable answer.
- `WikiPatcher` applies append patch and records revision.
- `WikiLint` reports missing provenance and stale page files.
- `WikiLint` reports invalid frontmatter, broken index links, and malformed log headings.
- `WikiLinks` extracts Markdown links, provenance links, and backlinks.

### Integration Tests

- Document ingestion completion triggers wiki compilation when enabled.
- Existing knowledge upload/list/delete APIs keep working.
- Wiki pages endpoint returns only pages for owned knowledge bases.
- Patch apply updates Markdown and DB state together.
- Chat wiki-first returns wiki answer when confidence passes.
- Chat fallback returns raw RAG answer when wiki misses.
- Chat fallback creates pending patch when eligible.
- Assisted ingest can hold source-page changes for review.
- `wiki_links` can be rebuilt from Markdown pages.

### Frontend Checks

- Existing Knowledge page upload/delete flows still work.
- Wiki tab loads page tree and page content.
- Patches tab applies and rejects patches.
- Lint tab displays warnings.

## Rollout Plan

### Phase 1: Wiki File Layer and DB Index

- Add wiki settings.
- Add wiki models and migration.
- Add `WikiStorage`.
- Add `WikiCompiler` for `schema.md`, `index.md`, `log.md`, and source pages.
- Add frontmatter generation.
- Add parseable `log.md` entries.
- Trigger compile after successful document ingestion.
- Add page list/get APIs.

### Phase 1.5: Index, Links, and Assisted Ingest

- Add index-first retrieval support.
- Add `wiki_links` extraction.
- Add pending cross-reference patches for topics/entities/related pages.
- Add `WIKI_INGEST_MODE`.
- Add assisted ingest review flow.

### Phase 2: Wiki-First Answer and Raw RAG Fallback

- Add `WikiRetriever`.
- Add `WikiAnswerer`.
- Add `WikiFallback`.
- Integrate with `ChatRagFlow` behind `WIKI_RAG_ENABLED`.
- Save answer mode and wiki metadata in prompt snapshots.

### Phase 3: Pending Writeback Patches

- Add `WikiWriteback`.
- Add `wiki_patches`.
- Generate pending patches after eligible raw RAG answers.
- Add patch list/apply/reject APIs.
- Add page revisions.

### Phase 4: Frontend Workspace

- Add Knowledge page tabs.
- Add Wiki page tree and Markdown preview.
- Add Patches tab.
- Add Lint tab.

### Phase 5: Enhanced Wiki Intelligence

- Add topic/entity page generation.
- Add contradiction detection.
- Add orphan page detection improvements.
- Add optional wiki semantic retrieval.
- Add low-risk auto-apply mode for FAQ append operations.
- Add assets/image support.
- Add answer artifact types for tables, charts, reports, and slide outlines.
- Add internal maintenance commands or CLI wrappers.

## Acceptance Criteria

- A completed document can produce a source wiki page, index update, and log entry.
- Generated pages include required frontmatter.
- `log.md` entries use the required parseable heading format.
- `index.md` participates in wiki retrieval before full-page BM25.
- Ingest creates pending cross-reference patches when topic/entity candidates are found.
- A user can browse wiki pages from the frontend.
- A wiki-only answer can return directly when confidence and citations pass.
- A wiki miss falls back to the existing raw RAG behavior.
- A useful raw RAG answer creates a pending wiki patch.
- Applying a patch updates Markdown, records a revision, and updates page metadata.
- Rejecting a patch preserves audit history and does not modify Markdown.
- Wiki failures do not break existing RAG.
- All automatic wiki additions include provenance.
