from app.core.config.modules.wiki import WikiSettings


def test_wiki_settings_defaults_match_phase1_plan():
    settings = WikiSettings()

    assert settings.WIKI_RAG_ENABLED is True
    assert settings.WIKI_WRITEBACK_MODE == "manual"
    assert settings.WIKI_INGEST_MODE == "auto"
    assert settings.WIKI_ANSWER_CONFIDENCE_THRESHOLD == 0.72
    assert settings.WIKI_RETRIEVER_TOP_K == 5
    assert settings.WIKI_STORAGE_DIR == "storage/wiki"
    assert settings.WIKI_MAX_PAGE_CHARS == 12000
    assert settings.WIKI_PATCH_CONFIDENCE_THRESHOLD == 0.70
    assert settings.WIKI_AUTO_COMPILE_ON_INGEST is True


def test_wiki_settings_reject_invalid_modes():
    settings = WikiSettings(
        WIKI_WRITEBACK_MODE="surprise",
        WIKI_INGEST_MODE="mystery",
    )

    assert settings.WIKI_WRITEBACK_MODE == "manual"
    assert settings.WIKI_INGEST_MODE == "auto"


def test_wiki_settings_clamps_numeric_values():
    settings = WikiSettings(
        WIKI_ANSWER_CONFIDENCE_THRESHOLD=5,
        WIKI_RETRIEVER_TOP_K=0,
        WIKI_MAX_PAGE_CHARS=10,
        WIKI_PATCH_CONFIDENCE_THRESHOLD=-1,
    )

    assert settings.WIKI_ANSWER_CONFIDENCE_THRESHOLD == 0.72
    assert settings.WIKI_RETRIEVER_TOP_K == 5
    assert settings.WIKI_MAX_PAGE_CHARS == 12000
    assert settings.WIKI_PATCH_CONFIDENCE_THRESHOLD == 0.70
