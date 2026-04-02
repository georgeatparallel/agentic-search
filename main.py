"""
FastAPI application for the Agentic Search system.

Provides:
- POST /api/search — run a topic query through the pipeline
- GET  /api/health — health check
- GET  / — serve the frontend UI
"""

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from pipeline import run_pipeline

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
async def search(req: SearchRequest):
    """
    Run the full agentic search pipeline for a topic query.
    Returns structured entity table with source provenance.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    logger.info(f"Search request: '{req.query}' (agent={'enabled' if req.enable_agent else 'disabled'})")

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
