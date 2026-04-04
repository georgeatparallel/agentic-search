"""
FastAPI application for the Agentic Search system.

Provides:
- POST /api/search — run a topic query through the pipeline
- GET  /api/health — health check
- GET  / — serve the frontend UI
"""

import asyncio
import logging
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from pipeline import run_pipeline

# --- Rate limiting ---
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "5"))  # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))     # seconds

_request_timestamps: dict[str, deque] = defaultdict(deque)
_search_semaphore = asyncio.Semaphore(1)  # one search at a time (LLM is single-threaded)


def _check_rate_limit(client_ip: str) -> None:
    """Sliding window rate limit. Raises 429 if exceeded."""
    now = time.monotonic()
    timestamps = _request_timestamps[client_ip]
    # Drop timestamps outside the current window
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        retry_after = int(RATE_LIMIT_WINDOW - (now - timestamps[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s. "
                   f"Retry after {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
    timestamps.append(now)

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# --- App ---
app = FastAPI(
    title="Agentic Search",
    description="Structured entity discovery from web search",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models ---
class SearchRequest(BaseModel):
    query: str
    enable_agent: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "query": "AI startups in healthcare",
                "enable_agent": True,
            }
        }


# --- Routes ---
@app.get("/api/health")
async def health():
    return {"status": "ok", "llm_provider": config.LLM_PROVIDER, "llm_model": config.LLM_MODEL}


@app.post("/api/search")
async def search(req: SearchRequest, request: Request):
    """
    Run the full agentic search pipeline for a topic query.
    Returns structured entity table with source provenance.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    if not _search_semaphore._value:
        raise HTTPException(status_code=429, detail="A search is already in progress. Please wait.")

    logger.info(f"Search request: '{req.query}' (agent={'enabled' if req.enable_agent else 'disabled'})")

    async with _search_semaphore:
        try:
            result = await run_pipeline(
                query=req.query,
                enable_agent=req.enable_agent,
            )
            return JSONResponse(content=result.to_dict())
        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# --- Frontend ---
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


@app.get("/")
async def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not found. Use POST /api/search for API access."}


# Mount static files if frontend directory exists
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# --- Entrypoint ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )
