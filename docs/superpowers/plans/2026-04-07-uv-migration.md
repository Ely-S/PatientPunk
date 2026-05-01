# uv + pyproject.toml Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace two `requirements.txt` files with a single root-level `pyproject.toml` managed by `uv`, targeting Python 3.13, with a GitHub Actions CI workflow that installs deps and runs tests.

**Architecture:** Single `pyproject.toml` at the repo root consolidates all runtime and dev dependencies. `uv lock` produces a deterministic `uv.lock` lockfile. GitHub Actions installs `uv`, runs `uv sync`, then `uv run pytest`. Existing pytest config migrates from `Scrapers/demographic_extraction/pytest.ini` into `[tool.pytest.ini_options]` in `pyproject.toml`.

**Tech Stack:** uv 0.8+, Python 3.13, GitHub Actions (`actions/setup-python`, `astral-sh/setup-uv`)

---

## File Map

| Action | Path |
|---|---|
| Create | `pyproject.toml` |
| Create | `uv.lock` (generated, not hand-edited) |
| Create | `.github/workflows/ci.yml` |
| Delete | `Scrapers/requirements.txt` |
| Delete | `src/requirements.txt` |
| Delete | `Scrapers/demographic_extraction/pytest.ini` |

---

### Task 1: Create `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "patientpunk"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "anthropic>=0.18.0",
    "python-dotenv>=1.0",
    "requests>=2.32",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["Scrapers/demographic_extraction/tests"]
```

- [ ] **Step 2: Generate the lockfile**

Run:
```bash
uv lock
```

Expected: `uv.lock` created at repo root, no errors. Output ends with `Resolved N packages`.

- [ ] **Step 3: Verify install from lock**

Run:
```bash
uv sync
```

Expected: uv creates `.venv/` and installs all packages. No errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add pyproject.toml and uv.lock for uv-managed dependencies"
```

---

### Task 2: Verify existing tests pass under uv

**Files:**
- Read: `Scrapers/demographic_extraction/tests/test_pipeline.py` (already reviewed — no changes needed)

The tests use `sys.path.insert(0, str(Path(__file__).parent.parent))` to make `discover_fields` importable directly. This works when run from the repo root.

- [ ] **Step 1: Run tests via uv**

Run:
```bash
uv run pytest Scrapers/demographic_extraction/tests/ -v
```

Expected: All tests pass. Output ends with something like:
```
============================= N passed in Xs ==============================
```

If tests fail with an import error on `discover_fields`, it means the path shim in the test file isn't resolving — debug by running:
```bash
uv run python -c "import sys; sys.path.insert(0, 'Scrapers/demographic_extraction'); from discover_fields import parse_json_response; print('ok')"
```

Do not proceed to Task 3 until tests pass.

---

### Task 3: Migrate pytest config and delete old files

**Files:**
- Delete: `Scrapers/demographic_extraction/pytest.ini`
- Delete: `Scrapers/requirements.txt`
- Delete: `src/requirements.txt`

- [ ] **Step 1: Confirm `testpaths` in `pyproject.toml` covers the test directory**

The `pyproject.toml` from Task 1 already sets:
```toml
[tool.pytest.ini_options]
testpaths = ["Scrapers/demographic_extraction/tests"]
```

This replaces the old `pytest.ini` which set `testpaths = tests` (relative to its own location).

- [ ] **Step 2: Run tests again to confirm config was picked up correctly**

Run:
```bash
uv run pytest -v
```

(No path argument — relies entirely on `testpaths` in `pyproject.toml`.)

Expected: Same N tests pass as in Task 2.

- [ ] **Step 3: Delete old files**

```bash
rm Scrapers/requirements.txt
rm src/requirements.txt
rm Scrapers/demographic_extraction/pytest.ini
```

- [ ] **Step 4: Run tests one final time to confirm nothing broke**

Run:
```bash
uv run pytest -v
```

Expected: All tests still pass.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "chore: remove requirements.txt files and pytest.ini, consolidated into pyproject.toml"
```

---

### Task 4: Add GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow directory and file**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: ["**"]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "0.8.11"

      - name: Set up Python 3.13
        run: uv python install 3.13

      - name: Install dependencies
        run: uv sync --locked

      - name: Run tests
        run: uv run pytest -v
```

**Why `--locked`:** Ensures CI uses exactly the pinned `uv.lock`, preventing "works locally, breaks in CI" from dependency drift.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow using uv and Python 3.13"
```

---

### Task 5: Push and verify CI

- [ ] **Step 1: Push the branch**

```bash
git push -u origin project-config
```

- [ ] **Step 2: Open the Actions tab**

Go to the repository on GitHub → Actions tab. Wait for the `CI` workflow to appear on the `project-config` branch push.

Expected: All steps green. If `Run tests` fails, check the log — most likely cause is the `sys.path.insert` in the test file not resolving `discover_fields` on the ubuntu runner. Fix by verifying the path shim resolves from the repo root (it should, since `pytest` is run from the repo root).

- [ ] **Step 3: Confirm and close**

Once CI is green, the migration is complete. No further action needed on this branch until it is merged to `main`.

---

## Self-Review

### Spec coverage
| Requirement | Task |
|---|---|
| Migrate from requirements.txt to pyproject.toml | Task 1 + Task 3 |
| Use uv | Task 1 (uv lock/sync), Task 4 (CI uses uv) |
| Python 3.13 | Task 1 (`requires-python = ">=3.13"`), Task 4 (`uv python install 3.13`) |
| GitHub Actions CI build step | Task 4 |
| Project builds (tests pass) | Task 2 + Task 5 |

### Placeholder scan
No TBDs, TODOs, or vague steps found. All code blocks are complete.

### Type consistency
No types involved — this is pure configuration.
