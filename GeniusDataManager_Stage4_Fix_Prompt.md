# Prompt: Fix Missing Stage & Clean Up GeniusDataManager Backend

Paste this into your AI coding assistant (Claude Code, Cursor, etc.) from the project root so it has access to the full `backend/` folder.

---

## Context

I'm working on **GeniusDataManager**, a FastAPI + SQLAlchemy (SQLite) backend for uploading data files, auto-detecting their schema, aligning them to a user-defined target schema, running analysis, and exporting results. The backend follows a staged pipeline structure:

```
backend/
  stage1_extraction/
  stage2_profiling/
  stage3_layout/
  stage5_export/
  routers/
  services/
  models/
  db.py
  database.py
  main.py
  tests/
  test_api_endpoints.py       <- currently at root, should be in tests/
  test_universal_pipeline.py  <- currently at root, should be in tests/
```

Two problems exist that need to be fixed:

1. **`stage4` is missing.** The pipeline goes extraction → profiling → layout → *(gap)* → export. Stage 4 should be the **analysis stage** — this is where the user's selected analysis type (sales analysis, trend analysis, comparison, summary stats, outlier detection) actually runs on the aligned data before export.
2. **There are two database setup files, `db.py` and `database.py`.** Only one should exist — duplicate engine/session/Base definitions risk creating two disconnected database contexts.

There's also a minor organizational issue: two test files sit at the project root instead of inside `tests/`.

---

## Task

Work through the following, in order, and **inspect the actual current contents of each file before changing anything** — do not assume what's inside `db.py`, `database.py`, or `main.py`; read them first.

### 1. Resolve the db.py / database.py duplication
- Open both files and determine which one defines the real SQLAlchemy `engine`, `SessionLocal`, and `Base` in active use (check what `main.py` and the files under `models/` actually import).
- Search the entire `backend/` tree for any import of the file that will be removed.
- Consolidate to a single source of truth (prefer `db.py` unless `database.py` is clearly the one in active use — tell me which you chose and why).
- Update every import across the codebase to point to the surviving file. Do not leave any dangling imports.

### 2. Create the missing `stage4_analysis` module
- Create `backend/stage4_analysis/` with:
  - `__init__.py`
  - `base.py` — defines a common interface/abstract base class every analysis type implements, e.g. a `run(dataframe, options: dict) -> dict` method, so the router can call any analysis type interchangeably.
  - `sales_analysis.py` — totals, averages, top-N by category, growth rate if a date column is present.
  - `trend_analysis.py` — time-bucketed aggregation (daily/weekly/monthly) with trend direction.
  - `comparison.py` — compares two segments (date ranges or category values) on chosen metric columns.
  - `summary_stats.py` — standard descriptive statistics per numeric column.
  - `outlier_detection.py` — IQR or z-score based flagging on chosen numeric columns.
- Each analysis class should raise a clear, catchable validation error (not a raw exception) if the data doesn't support the requested analysis (e.g. sales analysis requested with no numeric column).

### 3. Wire stage4 into the existing pipeline
- Find wherever stage1 → stage2 → stage3 → stage5 are currently chained (an orchestrator file, or logic inside `routers/`).
- Insert stage4 between stage3's output and stage5's input, so the full flow becomes: extraction → profiling → layout/alignment → **analysis** → export.
- Make sure the analysis type and any user-selected options (target columns, comparison type) flow through to stage4 correctly from whatever request model currently carries the user's configuration.

### 4. Consolidate the test files
- Move `test_api_endpoints.py` and `test_universal_pipeline.py` from the project root into `backend/tests/`.
- Fix any relative imports broken by the move.
- Add at least one new test file, `tests/test_stage4_analysis.py`, covering each of the five analysis types with a small synthetic DataFrame (a few rows is enough) — assert each returns the expected keys/shape and that the validation error fires correctly when given unsuitable data (e.g. no numeric column for sales analysis).

### 5. Update `.gitignore`
- Ensure the project has a `.gitignore` (create one if missing) that excludes: `__pycache__/`, `*.pyc`, `data/`, `*.db`, `venv/`.

### 6. Verify
- Run the full test suite (`pytest tests/` from `backend/`) and confirm everything passes.
- Start the server (`python start.py` from the project root) and confirm it boots with no import errors.
- Confirm `/docs` loads and that a request touching stage4 (even a minimal manual test) returns a sensible response, not a 500 or 404.

---

## Constraints

- Don't change the public API contract (`AlignmentConfig`, `AnalysisRequest`, endpoint paths) unless a genuine gap forces it — if it does, tell me what changed and why.
- Don't delete `database.py` or `db.py` outright before confirming which is safe to remove — rename to `<name>_OLD.py.bak` first as a safety net.
- Keep the analysis module pluggable: adding a sixth analysis type later should mean adding one new file, not touching the other five.

## Deliverable

At the end, give me:
1. A short summary of which db file you kept and what you changed.
2. The full contents of the new `stage4_analysis/` files.
3. Confirmation that tests pass and the server boots cleanly.
