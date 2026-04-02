"""
Configuration for the Agentic Search system.
Loads from environment variables with sensible defaults for local development.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Search ---
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
SEARCH_NUM_RESULTS = int(os.getenv("SEARCH_NUM_RESULTS", "10"))
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "brave")  # "brave" or "duckduckgo"

# --- Scraper ---
SCRAPE_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", "15"))  # seconds per page
SCRAPE_MAX_CONCURRENT = int(os.getenv("SCRAPE_MAX_CONCURRENT", "8"))
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# --- Chunking ---
CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "2000"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "200"))

# --- LLM ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" or "openai"
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")  # Only needed for cloud providers
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# --- Agent ---
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "2"))
AGENT_GAP_THRESHOLD = float(os.getenv("AGENT_GAP_THRESHOLD", "0.5"))  # re-search if >50% cells empty

# --- Server ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
