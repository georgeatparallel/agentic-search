# Agentic Search

A system that takes a topic query and produces a structured table of discovered entities with relevant attributes, sourced from the web. The system uses LLMs to dynamically determine what to extract, and employs an agentic loop to detect and fill information gaps.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![LLM](https://img.shields.io/badge/LLM-Qwen%202.5-orange)

## How It Works

```
Query → Schema Generation → Web Search → Scrape → Clean → Extract → Merge → Validate → Gap-Fill Loop → Results
```

1. **Schema Generation**: Given a topic like "AI startups in healthcare", the LLM determines the entity type ("company") and relevant attributes ("name", "founded", "funding", "focus_area", etc.)
2. **Web Search**: Queries Brave Search API (or DuckDuckGo fallback) for relevant pages
3. **Scrape & Clean**: Fetches pages concurrently with httpx, extracts main content with trafilatura, converts to clean markdown
4. **Extract**: LLM extracts structured entities from each page following the generated schema, with source quotes and confidence scores for every cell
5. **Merge**: Deduplicates entities across pages using fuzzy name matching, resolving conflicts by preferring higher-confidence values
6. **Agentic Loop**: Analyzes the results table for gaps. If too many cells are empty, automatically generates follow-up search queries, scrapes new pages, and merges additional findings

Every cell value is traceable to its source — hover over any value in the UI to see the supporting quote and source URL.

## Setup

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed for local LLM inference
- (Optional) [Brave Search API key](https://brave.com/search/api/) for higher quality search results

### 1. Install Ollama and pull the model

```bash
# Install Ollama (macOS)
brew install ollama

# Start Ollama server
ollama serve

# In another terminal, pull Qwen 2.5
ollama pull qwen2.5:7b

# Or for better quality on M4 Pro/Max (14B fits comfortably):
# ollama pull qwen2.5:14b
```

### 2. Clone and set up the project

```bash
git clone <your-repo-url>
cd agentic-search

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — add your BRAVE_API_KEY if you have one
```

### 3. Run

```bash
python main.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### API Usage

```bash
# Health check
curl http://localhost:8000/api/health

# Run a search
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "AI startups in healthcare", "enable_agent": true}'
```

## Architecture

See [architecture.md](architecture.md) for detailed design decisions and trade-offs.

### Project Structure

```
agentic-search/
├── main.py                # FastAPI app, routes, static serving
├── pipeline.py            # Orchestrates the full pipeline
├── config.py              # Environment-based configuration
├── search/
│   ├── brave.py           # Brave Search API client
│   └── fallback.py        # DuckDuckGo fallback
├── scraper/
│   ├── fetcher.py         # Async HTTP fetching (httpx)
│   ├── cleaner.py         # Content extraction (trafilatura)
│   └── chunker.py         # Text chunking for long pages
├── extractor/
│   ├── schema.py          # Dynamic schema generation via LLM
│   ├── extract.py         # Per-page entity extraction via LLM
│   ├── merge.py           # Cross-page deduplication & merging
│   └── validate.py        # Gap detection & follow-up query gen
├── agent/
│   └── loop.py            # Agentic re-search loop
├── llm/
│   └── client.py          # Unified LLM client (Ollama / OpenAI)
├── frontend/
│   └── index.html         # Single-page browser UI
├── architecture.md        # Design decisions blueprint
├── requirements.txt
└── .env.example
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Modular monolith | Simple to run and deploy; clean separation for testability |
| Framework | FastAPI | Async support for concurrent scraping; auto OpenAPI docs |
| Search | Brave + DDG fallback | 2,000 free/month; DDG as zero-cost backup |
| Scraping | httpx + BeautifulSoup | Fast, low memory; no browser overhead |
| Cleaning | trafilatura + html2text | Best signal-to-noise for LLM consumption |
| LLM | Qwen 2.5 via Ollama | Free, local, competitive quality on M4 hardware |
| Extraction | Dynamic schema + tracing | Adapts to any query; every value has provenance |
| Dedup | Fuzzy string matching | Simple and effective; no embedding dependency |
| Frontend | Vanilla HTML/JS | No build step; focus effort on pipeline quality |

## Known Limitations

- **No JavaScript rendering**: Static scraping only (httpx). JS-heavy SPAs may return empty content.
- **Local LLM speed**: Qwen 2.5 7B on CPU/Metal is slower than cloud APIs. A full query takes 30-120s depending on page count.
- **No caching**: Repeated queries re-execute the full pipeline.
- **Simple deduplication**: Uses fuzzy string matching, not embeddings. May miss non-obvious duplicates.
- **Rate limits**: No rate limiting on the API endpoint itself.
- **Extraction quality**: Dependent on LLM capability. Smaller models may hallucinate or miss entities.

## Deployment on AWS

For AWS free tier (t2.micro, 1GB RAM):

1. Switch `LLM_PROVIDER` to `openai` and use a cloud LLM API (OpenRouter, DeepSeek, etc.)
2. Local Ollama won't run on 1GB RAM
3. The rest of the stack (FastAPI, httpx, scraping) runs fine on t2.micro

```bash
# On EC2:
sudo apt update && sudo apt install python3-pip python3-venv nginx
# ... clone, venv, pip install, configure .env with cloud LLM
# Run with: uvicorn main:app --host 0.0.0.0 --port 8000
```

## Cost

| Component | Cost |
|-----------|------|
| Brave Search (2,000 free/month) | $0 |
| Qwen via Ollama (local) | $0 |
| AWS t2.micro (free tier) | $0 |
| **Total (local dev)** | **$0** |

If using cloud LLMs for deployment: ~$0.01–0.05 per query depending on model.

## License

MIT
