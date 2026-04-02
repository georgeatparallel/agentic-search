# Agentic Search

## What this is
Agentic search system: query → web search → scrape → LLM extraction → structured table with source provenance.

## How to run
- `ollama serve` in one terminal, then `python main.py` in another
- Opens at http://localhost:8000
- Needs `qwen2.5:7b` pulled in Ollama

## Architecture
See architecture.md for all design decisions. That file is the living blueprint — update it when making changes.

## Key technical details
- Python 3.11+ / FastAPI / async throughout
- LLM: Qwen 2.5 via Ollama (local), switchable to OpenAI-compatible APIs via config
- Search: Brave API primary, DuckDuckGo fallback
- Scraping: httpx + BeautifulSoup (no headless browser)
- Content cleaning: trafilatura + html2text
- All LLM calls go through llm/client.py

## Testing
`python -m pytest tests/ -v`

## Conventions
- Update architecture.md when making design changes
- Keep modules independent — each file in search/, scraper/, extractor/ should work standalone
- All config via environment variables (config.py reads .env)
EOF