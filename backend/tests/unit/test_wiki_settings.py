import pytest

from app.core.config.modules.wiki import WikiSettings


WIKI_ENV_KEYS = (
    "WIKI_RAG_ENABLED",
    "WIKI_WRITEBACK_MODE",
    "WIKI_INGEST_MODE",
    "WIKI_ANSWER_CONFIDENCE_THRESHOLD",
    "WIKI_RETRIEVER_TOP_K",
    "WIKI_STORAGE_DIR",
    "WIKI_MAX_PAGE_CHARS",
    "WIKI_PATCH_CONFIDENCE_THRESHOLD",
    "WIKI_AUTO_COMPILE_ON_INGEST",
)


def clear_wiki_env(monkeypatch):
    for key in WIKI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def isolate_wiki_env(monkeypatch):
    clear_wiki_env(monkeypatch)


def test_wiki_settings_defaults_match_phase1_plan():
    settings = WikiSettings(_env_file=None)

    assert settings.WIKI_RAG_ENABLED is True
    assert settings.WIKI_WRITEBACK_MODE == "manual"
    assert settings.WIKI_INGEST_MODE == "auto"
    assert settings.WIKI_ANSWER_CONFIDENCE_THRESHOLD == 0.72
    assert settings.WIKI_RETRIEVER_TOP_K == 5
    assert settings.WIKI_STORAGE_DIR == "storage/wiki"
    assert settings.WIKI_MAX_PAGE_CHARS == 12000
    assert settings.WIKI_PATCH_CONFIDENCE_THRESHOLD == 0.70
    assert settings.WIKI_AUTO_COMPILE_ON_INGEST is True


def test_wiki_settings_defaults_ignore_wiki_environment(monkeypatch):
    monkeypatch.setenv("WIKI_RETRIEVER_TOP_K", "9")

    clear_wiki_env(monkeypatch)
    settings = WikiSettings(_env_file=None)

    assert settings.WIKI_RETRIEVER_TOP_K == 5


def test_wiki_settings_reject_invalid_modes():
    settings = WikiSettings(
        WIKI_WRITEBACK_MODE="surprise",
        WIKI_INGEST_MODE="mystery",
        _env_file=None,
    )

    assert settings.WIKI_WRITEBACK_MODE == "manual"
    assert settings.WIKI_INGEST_MODE == "auto"


def test_wiki_settings_clamps_numeric_values():
    settings = WikiSettings(
        WIKI_ANSWER_CONFIDENCE_THRESHOLD=5,
        WIKI_RETRIEVER_TOP_K=0,
        WIKI_MAX_PAGE_CHARS=10,
        WIKI_PATCH_CONFIDENCE_THRESHOLD=-1,
        _env_file=None,
    )

    assert settings.WIKI_ANSWER_CONFIDENCE_THRESHOLD == 0.72
    assert settings.WIKI_RETRIEVER_TOP_K == 5
    assert settings.WIKI_MAX_PAGE_CHARS == 12000
    assert settings.WIKI_PATCH_CONFIDENCE_THRESHOLD == 0.70
