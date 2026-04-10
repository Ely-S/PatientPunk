"""Pytest path bootstrap for repo-root imports."""

from __future__ import annotations

import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_TMP_ROOT = Path(tempfile.gettempdir()) / "patientpunk_pytest"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_path() -> Path:
    """Provide a workspace-local temp directory on Windows/OneDrive setups."""
    WORKSPACE_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = WORKSPACE_TMP_ROOT / f"pytest-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
