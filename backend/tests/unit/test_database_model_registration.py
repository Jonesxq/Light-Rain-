import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_mysql_startup_registers_all_foreign_key_targets():
    code = textwrap.dedent(
        """
        from app.core.database.mysql import _register_sqlmodel_models
        from sqlmodel import SQLModel

        _register_sqlmodel_models()

        for table in SQLModel.metadata.tables.values():
            for foreign_key in table.foreign_keys:
                foreign_key.column

        assert "knowledge_bases" in SQLModel.metadata.tables
        assert "kb_documents" in SQLModel.metadata.tables
        assert "wiki_pages" in SQLModel.metadata.tables
        """
    )
    env = os.environ.copy()
    env["ENV"] = "test"
    env.setdefault("JWT_SECRET_KEY", "test-secret")
    backend_root = Path(__file__).parents[2]

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr + result.stdout
