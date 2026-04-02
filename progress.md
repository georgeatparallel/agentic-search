# Agentic Search — Progress Log

## Session 1 — 2026-04-02

### Refactored directory structure
Moved all flat-file modules into the subdirectory layout defined in `architecture.md`.

```
search/brave.py          search/fallback.py
scraper/fetcher.py       scraper/cleaner.py       scraper/chunker.py
extractor/schema.py      extractor/extract.py     extractor/merge.py      extractor/validate.py
agent/loop.py
llm/client.py
frontend/index.html
tests/test_search.py     tests/test_scraper.py    tests/test_extractor.py
```

No import changes needed — `pipeline.py` and `loop.py` already used the correct module paths.

---

### Set up Poetry
Replaced `requirements.txt` with Poetry (`pyproject.toml` + `poetry.lock`).

- Production deps: `fastapi`, `uvicorn`, `httpx`, `beautifulsoup4`, `trafilatura`, `html2text`, `duckduckgo-search`, `python-dotenv`, `rich`
- Dev deps: `pytest`, `pytest-asyncio`
- `poetry.lock` added to `.gitignore` (regenerated per environment)

---

### Installed Ollama + pulled model
- Installed Ollama 0.19.0 via Homebrew
- Pulled `qwen2.5:7b` (4.7 GB) — the model used for schema generation and entity extraction

---

### Ran app and tests
- All 14 tests pass across `test_search`, `test_scraper`, `test_extractor`
- Fixed a bug in `test_merge_prefers_higher_confidence`: fixture used `"Acme"` vs `"Acme Corp"` (similarity 0.62, below the 0.75 merge threshold), so they were never merged. Changed second entity name to `"Acme"` to correctly test confidence-based merging.
- End-to-end pipeline verified: schema generation, Brave search, page fetching, LLM extraction all working. Full run takes ~7 min with `qwen2.5:7b` locally.

---

### Updated `.gitignore`
Added: `__pycache__/`, `*.py[cod]`, `poetry.lock`, `.env.*`, `.venv/`, `.pytest_cache/`, `.coverage`, `.vscode/`, `.idea/`, `.DS_Store`, `*.log`, `dist/`, `build/`

---

### UI: removed spinner from status messages
Stripped the animated spinner element from each status log line in `frontend/index.html` — text-only display.

---

## Known issues / next steps

- Local LLM is slow (~20s per page extraction with 7B model). Consider switching to a faster model or cloud API for development.
- No `.env.example` file yet — contributors have no reference for required env vars.
- No rate limiting on `POST /api/search`.
- Agentic loop capped at 2 iterations (see `AGENT_MAX_ITERATIONS` in `config.py`).
