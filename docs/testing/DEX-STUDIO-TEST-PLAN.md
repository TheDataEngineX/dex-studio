# DEX Studio Test Plan

> Comprehensive QA Test Plan covering Manual Testing, Automated Testing, and Edge Cases

**Stack:** Python 3.13+ · NiceGUI 3.x · DuckDB · pytest · Playwright
**Version:** `uv run poe version`

______________________________________________________________________

## 1. Manual Test Plan

### 1.1 Exploratory Scenarios by Module

| ID | Module | Scenario | Expected Result |
|----|--------|---------|----------|----------------|
| M-001 | CareerDEX | Add new job application with all fields filled | Entry saved, appears in list |
| M-002 | CareerDEX | Add application, update status through full lifecycle | Status transitions correctly |
| M-003 | CareerDEX | Delete application with confirmation | Entry removed from DB |
| M-004 | AI/RAG | Create new collection, add documents | Collection searchable |
| M-005 | AI/RAG | Run retrieval query with no matches | Empty results, no crash |
| M-006 | ML/Experiments | Create experiment, log metrics | Metrics displayed in chart |
| M-007 | ML/Models | Register model, upload model card | Card renders correctly |
| M-008 | System | View app status page | All services show health |
| M-009 | All | Startup app with no network | App launches, offline mode works |

### 1.2 UI/UX Checks

| ID | Check | Validation |
|----|-------|------------|
| U-001 | Page load speed | All pages load < 2s |
| U-002 | Responsive layout | 800x600, 1280x720, 1920x1080 all render |
| U-003 | Form validation | Invalid inputs show clear errors |
| U-004 | Empty states | All list views show helpful empty message |
| U-005 | Loading states | Async ops show spinner/skeleton |
| U-006 | Error messages | HTTP errors display user-friendly text |
| U-007 | Navigation | All links/breadcrumbs work |
| U-008 | Theme toggle | Light/dark mode persists |

### 1.3 Edge Cases - Manual

| ID | Scenario | Expected Result |
|----|----------|----------------|
| E-001 | Empty text input in required field | Validation error shown |
| E-002 | Upload file > 50MB | Error message, upload blocked |
| E-003 | Upload invalid file type (e.g., .exe) | Error, file rejected |
| E-004 | Rapidly click submit button | Debounced, single submission |
| E-005 | Navigate away during form edit | Warning about unsaved changes |
| E-006 | Very long text (10KB+) in textarea | Renders without hang |
| E-007 | Special characters in input (quotes, newlines) | Escaped correctly |
| E-008 | Duplicate entry submission | Second submission blocked |

______________________________________________________________________

## 2. Automated Test Suite Strategy

### 2.1 Test Directory Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests (fast, isolated)
│   ├── careerdex/
│   │   ├── test_tracker.py
│   │   ├── test_job_search.py
│   │   ├── test_progress.py
│   │   └── test_models_*.py
│   └── test_*.py
├── integration/              # Integration tests (DB, API)
│   └── test_app.py
└── e2e/                     # Browser tests (slow, full)
    └── test_resume_matcher.mjs
```

### 2.2 Test Types

| Type | Coverage | Run Time | When |
|------|----------|----------|------|
| Unit | Functions, classes, models | < 30s | Every commit |
| Integration | DB, API endpoints | < 2min | PR/Merge |
| E2E | Full browser flows | < 10min | Release |

### 2.3 Unit Test Pattern

```python
"""Unit tests for <Module>."""

from __future__ import annotations

from pathlib import Path

import pytest

from dex_studio.careerdex.services.tracker import ApplicationTracker
from dex_studio.careerdex.models.application import ApplicationEntry


@pytest.fixture()
def tracker(tmp_path: Path) -> ApplicationTracker:
    return ApplicationTracker(db_path=tmp_path / "test.duckdb")


@pytest.fixture()
def entry() -> ApplicationEntry:
    return ApplicationEntry(company="Acme", position="Data Engineer")


class TestAdd:
    def test_returns_entry(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        result = tracker.add(entry)
        assert result.id == entry.id

    def test_persists(self, tracker: ApplicationTracker, entry: ApplicationEntry) -> None:
        tracker.add(entry)
        assert tracker.get(entry.id) is not None


class TestGet:
    def test_missing_returns_none(self, tracker: ApplicationTracker) -> None:
        assert tracker.get("does-not-exist") is None


class TestListAll:
    def test_empty(self, tracker: ApplicationTracker) -> None:
        assert tracker.list_all() == []
```

### 2.4 Integration Test Pattern

```python
"""Integration tests for app startup and routing."""

import pytest
from niceguify import UI


def test_app_mounts(ui: UI) -> None:
    """App mounts without error."""
    ui.navigate("/career")
    assert ui.should_display("CareerDEX")


def test_career_page_loads(ui: UI) -> None:
    """Career page shows dashboard."""
    ui.navigate("/career")
    assert ui.should_display("Dashboard")
```

### 2.5 E2E Test Pattern (Playwright)

```javascript
// tests/e2e/test_resume_matcher.mjs
import { test, expect } from '@playwright/test';

test('add new application', async ({ page }) => {
  await page.goto('http://localhost:7860/career');
  await page.click('text=Add Application');
  await page.fill('input[placeholder="Company"]', 'Acme');
  await page.fill('input[placeholder="Position"]', 'SWE');
  await page.click('text=Save');
  await expect(page.locator('text=Acme')).toBeVisible();
});
```

______________________________________________________________________

## 3. Edge Case Scenarios - Python

### 3.1 NoneType Handling

| ID | Scenario | Expected | Test |
|----|----------|----------|------|
| N-001 | Pass `None` to function requiring str | TypeError/ValueError | `with pytest.raises(ValueError): func(None)` |
| N-002 | Database query returns NULL | Converted to `None` or default | ` assert row.field is None` |
| N-003 | Optional field not provided | Uses default or `None` | `result = func(); assert result.opt is None` |
| N-004 | Dictionary `.get()` on missing key | Returns `None` | ` assert d.get("x") is None` |

### 3.2 KeyError Scenarios

| ID | Scenario | Expected | Test |
|----|----------|----------|------|
| K-001 | Access missing dict key with `[]` | Raises KeyError | `with pytest.raises(KeyError): d["missing"]` |
| K-002 | Missing required config key | ConfigError with message | `with pytest.raises(ConfigError): load({})` |
| K-003 | Missing relation in join | Empty or error | Handle gracefully |

### 3.3 TypeError Scenarios

| ID | Scenario | Expected | Test |
|----|----------|----------|------|
| T-001 | Pass str where int expected | TypeError | `with pytest.raises(TypeError): func("42")` |
| T-002 | Pass list where dict expected | TypeError | `with pytest.raises(TypeError): func([1,2,3])` |
| T-003 | Call non-callable as function | TypeError | `with pytest.raises(TypeError): func(fn)` |
| T-004 | Unsupported operand types | TypeError | `with pytest.raises(TypeError): func(1 + "a")` |

### 3.4 DuckDB Edge Cases

| ID | Scenario | Expected | Test |
|----|----------|----------|------|
| D-001 | Insert into non-existent table | OperationalError | Handle in init |
| D-002 | Query with malformed SQL | SyntaxError | Catch and log |
| D-003 | Concurrent writes to same DB | Handle locking | Use connection pooling |
| D-004 | Huge result set (> 100k rows) | MemoryError or streaming | Test with LIMIT |

### 3.5 Data Edge Cases

| ID | Scenario | Expected | Test |
|----|----------|----------|------|
| X-001 | Empty input string | Validation error | Trimmed and rejected |
| X-002 | Whitespace-only input | Trimmed, then empty | Validation error |
| X-003 | Unicode characters | Stored correctly | `assert "日本" in db` |
| X-004 | JSON in text field | Escaped/stored | Round-trip preserved |
| X-005 | Very long company name (>500) | Truncated or error | Handle in model |

______________________________________________________________________

## 4. Running Tests

```bash
# All tests
uv run poe test

# Unit only (fast)
pytest tests/unit/

# Integration only
pytest tests/integration/

# E2E only (requires app running)
pytest tests/e2e/

# With coverage
pytest --cov=src/dex_studio tests/unit/

# Specific module
pytest tests/unit/careerdex/test_tracker.py

# By marker
pytest -m unit          # unit tests only
pytest -m integration  # integration tests only
pytest -m slow         # slow tests
```

______________________________________________________________________

## 5. Test Markers

Define in `pyproject.toml`:

```toml
[tool.pytest.markers]
unit = "Unit tests - fast, isolated"
integration = "Integration tests - DB, API"
slow = "Tests taking > 5s"
e2e = "End-to-end browser tests"
```

______________________________________________________________________

## 6. CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv install
      - run: uv run poe lint
      - run: uv run poe typecheck
      - run: uv run poe test
```

______________________________________________________________________

*Generated: 2026-04-10*
