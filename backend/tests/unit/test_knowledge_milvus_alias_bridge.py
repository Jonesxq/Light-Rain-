"""Tests for Milvus alias bridge ordering and retry behavior."""

from app.services.knowledge import KnowledgeService
from app.services.knowledge.ingest import KnowledgeIngest
from app.services.knowledge.retrieval import KnowledgeRetrieval
from app.services.knowledge.runtime import KnowledgeRuntime
from app.services.knowledge.storage import KnowledgeStorage
from app.services.knowledge import runtime as core_module


def _new_service() -> KnowledgeService:
    service = KnowledgeService.__new__(KnowledgeService)
    service._runtime = KnowledgeRuntime(service)
    service._storage = KnowledgeStorage(service)
    service._retrieval = KnowledgeRetrieval(service)
    service._ingest = KnowledgeIngest(service)
    service._ops = (service._runtime, service._storage, service._retrieval, service._ingest)
    service.embeddings = object()
    return service


def test_bridge_alias_before_milvus_init(monkeypatch):
    service = _new_service()
    events: list[str] = []
    aliases: set[str] = set()
    connect_calls: list[dict] = []

    class _FakeMilvusClient:
        def __init__(self, **_kwargs):
            self._using = "cm-prewarm"

        def close(self):
            events.append("client_close")

    def _fake_has_connection(alias: str) -> bool:
        events.append(f"has:{alias}")
        return alias in aliases

    def _fake_connect(*, alias: str, db_name: str = "default", **kwargs):
        events.append(f"connect:{alias}")
        aliases.add(alias)
        connect_calls.append({"alias": alias, "db_name": db_name, "kwargs": kwargs})

    class _FakeMilvus:
        def __init__(
            self,
            embedding_function,
            connection_args,
            collection_name,
            auto_id,
            drop_old,
        ):
            events.append("milvus_init")
            assert embedding_function is service.embeddings
            assert collection_name == "kb_7"
            assert auto_id is True
            assert drop_old is False
            assert connection_args["uri"]
            assert "cm-prewarm" in aliases
            self.alias = "cm-prewarm"

    monkeypatch.setattr(core_module, "MilvusClient", _FakeMilvusClient)
    monkeypatch.setattr(core_module, "Milvus", _FakeMilvus)
    monkeypatch.setattr(core_module.milvus_connections, "has_connection", _fake_has_connection)
    monkeypatch.setattr(core_module.milvus_connections, "connect", _fake_connect)

    store = service._get_vector_store(7)

    assert store.alias == "cm-prewarm"
    assert connect_calls
    assert connect_calls[0]["alias"] == "cm-prewarm"
    assert connect_calls[0]["db_name"] == ""
    assert events.index("connect:cm-prewarm") < events.index("milvus_init")


def test_existing_alias_does_not_reconnect(monkeypatch):
    service = _new_service()
    aliases = {"cm-existing"}
    connect_calls: list[dict] = []

    class _FakeMilvusClient:
        def __init__(self, **_kwargs):
            self._using = "cm-existing"

        def close(self):
            return None

    def _fake_has_connection(alias: str) -> bool:
        return alias in aliases

    def _fake_connect(*, alias: str, db_name: str = "default", **kwargs):
        connect_calls.append({"alias": alias, "db_name": db_name, "kwargs": kwargs})

    class _FakeMilvus:
        def __init__(self, *args, **kwargs):
            self.alias = "cm-existing"

    monkeypatch.setattr(core_module, "MilvusClient", _FakeMilvusClient)
    monkeypatch.setattr(core_module, "Milvus", _FakeMilvus)
    monkeypatch.setattr(core_module.milvus_connections, "has_connection", _fake_has_connection)
    monkeypatch.setattr(core_module.milvus_connections, "connect", _fake_connect)

    store = service._get_vector_store(7)

    assert store.alias == "cm-existing"
    assert connect_calls == []


def test_build_connection_args_with_auth(monkeypatch):
    service = _new_service()

    monkeypatch.setattr(core_module.settings.llm, "MILVUS_URI", "http://localhost:19530/test_db")
    monkeypatch.setattr(core_module.settings.llm, "MILVUS_USER", "alice")
    monkeypatch.setattr(core_module.settings.llm, "MILVUS_PASSWORD", "secret")

    args = service._build_milvus_connection_args()

    assert args == {
        "uri": "http://localhost:19530/test_db",
        "user": "alice",
        "password": "secret",
    }


def test_retry_once_when_connection_not_exist(monkeypatch):
    service = _new_service()
    ensure_calls: list[dict] = []
    create_count = {"count": 0}

    def _fake_ensure(connection_args):
        ensure_calls.append(dict(connection_args))
        return "cm-retry"

    class _FakeMilvus:
        def __init__(self, *args, **kwargs):
            create_count["count"] += 1
            if create_count["count"] == 1:
                raise core_module.ConnectionNotExistException(message="should create connection first.")
            self.alias = "cm-retry"

    monkeypatch.setattr(service, "_build_milvus_connection_args", lambda: {"uri": "http://localhost:19530"})
    monkeypatch.setattr(service, "_ensure_legacy_connection_alias", _fake_ensure)
    monkeypatch.setattr(core_module, "Milvus", _FakeMilvus)
    monkeypatch.setattr(core_module.milvus_connections, "has_connection", lambda _alias: True)

    store = service._get_vector_store(9)

    assert store.alias == "cm-retry"
    assert create_count["count"] == 2
    assert len(ensure_calls) == 2
