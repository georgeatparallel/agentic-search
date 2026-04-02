# Agentic Search — Architecture & Design Decisions

> This document is the living blueprint for the project. All design decisions are recorded here.

## Overview

An agentic search system that takes a topic query, searches the web, scrapes results, uses LLMs to extract structured entity data, and returns a traceable table of results.

## Architecture Diagram

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│  User Query  │────▶│  Search API  │────▶│   Scraper    │────▶│  LLM Extract  │
│  (FastAPI)   │     │ (Brave/DDG)  │     │(httpx + BS4) │     │  (Qwen/Ollama)│
└─────────────┘     └──────────────┘     └──────────────┘     └───────┬───────┘
                                                                      │
      ┌───────────────────────────────────────────────────────────────┘
      ▼
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│  Merge &     │────▶│  Validate &  │────▶│  Return JSON  │
│  Deduplicate │     │  Gap Detect  │     │  + Render UI  │
└──────────────┘     └──────────────┘     └───────────────┘
      │                                          ▲
      │         ┌──────────────┐                 │
      └────────▶│ Agentic Loop │─────────────────┘
                │ (Re-search)  │
                └──────────────┘
```

## Decision Log

### D1: Architecture Style — Modular Monolith
- **Choice:** Single codebase with clean module separation
- **Why:** Simple to run locally and deploy on AWS free tier (t2.micro, 1GB RAM). Shows design maturity without over-engineering.
- **Trade-off:** Cannot scale individual components independently, but irrelevant at this scale.

### D2: Language & Framework — Python + FastAPI
- **Choice:** Python 3.11+ with FastAPI
- **Why:** Best ecosystem for scraping (httpx, BeautifulSoup), LLM calls, and data processing. FastAPI provides async support (critical for concurrent scraping) and auto-generated OpenAPI docs.
- **Trade-off:** Slower runtime than Go/Rust, but irrelevant — bottleneck is network I/O and LLM inference.

### D3: Search API — Brave Search (primary) + DuckDuckGo (fallback)
- **Choice:** Brave Search API with 2,000 free queries/month. DuckDuckGo as zero-cost fallback.
- **Why:** Generous free tier. Clean JSON API. Good result quality.
- **Trade-off:** Smaller index than Google. Mitigated by DDG fallback.
- **Cost:** $0 within free tier.

### D4: Web Scraping — httpx + BeautifulSoup (lightweight)
- **Choice:** Async httpx for fetching, BeautifulSoup for parsing. No headless browser.
- **Why:** Fast (100-500ms per page), low memory, async concurrency. No browser overhead.
- **Trade-off:** Cannot handle JavaScript-rendered SPAs. Acceptable for v0 — most informational pages are server-rendered.
- **Cost:** $0, minimal resource usage.
- **Future:** Can add Playwright fallback or Jina Reader for JS-heavy pages.

### D5: Content Cleaning — trafilatura + html2text
- **Choice:** trafilatura extracts main content (strips nav/footer/ads), then html2text converts to markdown.
- **Why:** Highest signal-to-noise ratio for LLM consumption. Reduces token waste.
- **Trade-off:** Occasionally strips too aggressively on unusual layouts.

### D6: LLM — Qwen 2.5 via Ollama (local)
- **Choice:** Qwen 2.5 (7B or 14B) running locally through Ollama.
- **Why:** Open source, free, no API costs. Competitive quality with proprietary models. Runs well on M4 MacBook Pro with Metal GPU acceleration.
- **Trade-off:** Slower than cloud APIs. Quality slightly below GPT-4o for complex extraction. Cannot run on AWS t2.micro (need to switch to cloud API for deployment).
- **Cost:** $0.
- **Deployment plan:** Switch to cloud LLM API (OpenRouter/DeepSeek) for AWS deployment.

### D7: Extraction Strategy — Multi-level
- **Level 1:** Dynamic schema generation from query (LLM determines entity type + attributes)
- **Level 2:** Per-page extraction with source tracing (quotes + confidence scores)
- **Level 3:** Cross-page merge with fuzzy deduplication
- **Level 4 (stretch):** Agentic gap-filling loop

### D8: Frontend — Single-page vanilla HTML/JS
- **Choice:** One index.html served by FastAPI static files.
- **Why:** No build step, trivial to deploy, focuses effort on backend quality.
- **Trade-off:** Less polished than React. Acceptable — challenge is about search quality.

### D9: Deployment — AWS EC2 t2.micro
- **Target:** Ubuntu on t2.micro (1 vCPU, 1GB RAM)
- **Constraints:** No headless browsers, no local LLMs. Must use cloud LLM API.
- **Plan:** uvicorn behind nginx, port 80.

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `main.py` | FastAPI app, routes, static file serving |
| `config.py` | Environment variables, model settings, thresholds |
| `pipeline.py` | Orchestrates full search→extract→merge flow |
| `search/brave.py` | Brave Search API client |
| `search/fallback.py` | DuckDuckGo fallback search |
| `scraper/fetcher.py` | Async HTTP fetching with httpx |
| `scraper/cleaner.py` | Content extraction (trafilatura + html2text) |
| `scraper/chunker.py` | Text chunking for long documents |
| `extractor/schema.py` | Dynamic schema generation via LLM |
| `extractor/extract.py` | Per-page entity extraction via LLM |
| `extractor/merge.py` | Cross-page entity merging & deduplication |
| `extractor/validate.py` | Validation & gap detection |
| `agent/loop.py` | Agentic re-search loop for gap filling |
| `llm/client.py` | Unified LLM client (Ollama, OpenAI-compatible) |
| `frontend/index.html` | Browser UI |

## Data Flow

1. **Input:** User submits topic query (e.g., "AI startups in healthcare")
2. **Schema Generation:** LLM analyzes query → determines entity type + attributes
3. **Search:** Brave API returns top 10 URLs with snippets
4. **Fetch:** httpx fetches pages concurrently (max 10 concurrent)
5. **Clean:** trafilatura + html2text → clean markdown per page
6. **Chunk:** Split long pages into ~2000-token chunks with overlap
7. **Extract:** LLM extracts entities from each chunk following the schema
8. **Merge:** Deduplicate entities across pages (fuzzy name matching)
9. **Validate:** Check for contradictions, assign confidence scores
10. **Gap Detection:** Identify empty cells in the table
11. **Agentic Loop:** Generate follow-up queries for gaps, repeat steps 3-9
12. **Output:** JSON response + rendered HTML table with source links

## Known Limitations (v0)

- No JavaScript rendering (static scraping only)
- Local LLM quality depends on hardware and model size
- No caching layer (repeated queries re-execute everything)
- No rate limiting on the API
- Entity deduplication uses simple fuzzy matching, not embeddings
- Agentic loop has a hard cap of 2 iterations to control cost/latency
