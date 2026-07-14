from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "notebooks" / "build_notebook.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_notebook", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_notebook_preserves_memory_db_path():
    module = _load_module()

    nb = module.build_notebook([("md", "# test")], db_path=":memory:")

    setup = nb.cells[0].source
    assert "DB_PATH = ':memory:'" in setup
    assert 'if DB_PATH != ":memory:" and not os.path.exists(DB_PATH):' in setup


def test_build_notebook_keeps_custom_db_path_block():
    module = _load_module()
    custom_block = 'DB_PATH = "file:memdb1?mode=memory&cache=shared"\nconn = sqlite3.connect(DB_PATH, uri=True)'

    nb = module.build_notebook(
        [("md", "# test")],
        db_path="ignored.db",
        db_path_block=custom_block,
    )

    assert custom_block in nb.cells[0].source


def test_build_notebook_uses_uri_connect_for_file_uri():
    module = _load_module()
    db_path = "file:memdb1?mode=memory&cache=shared"

    nb = module.build_notebook([("md", "# test")], db_path=db_path)

    setup = nb.cells[0].source
    assert f"DB_PATH = {db_path!r}" in setup
    assert "conn = sqlite3.connect(DB_PATH, uri=True)" in setup
    assert 'if DB_PATH != ":memory:" and not os.path.exists(DB_PATH):' not in setup


def test_build_notebook_resolves_filesystem_paths(tmp_path):
    module = _load_module()
    db_path = tmp_path / "patientpunk.db"

    nb = module.build_notebook([("md", "# test")], db_path=db_path)

    setup = nb.cells[0].source
    assert repr(db_path.resolve().as_posix()) in setup
