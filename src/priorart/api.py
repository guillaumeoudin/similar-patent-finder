"""Small web service: a search endpoint, an answer endpoint, and the web page.

Needs: pip install -e '.[api]'
Run with: uvicorn priorart.api:app   (listens on 127.0.0.1 only, there is no login)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from priorart.answer import answer_query, make_answerer
from priorart.config import load_settings
from priorart.embeddings import make_embedder
from priorart.search import SearchResult, hybrid_search
from priorart.store import Store

STATIC = Path(__file__).parent / "static"
DISCLAIMER = "This is not legal advice."

app = FastAPI(title="Similar Patent Finder")
_settings = load_settings()
_state: dict = {}


class QueryRequest(BaseModel):
    query: str = Field(min_length=20, max_length=20000)


def get_engine():
    """Create the embedder and the database connection on first use."""
    if not _state:
        _state["embedder"] = make_embedder(_settings)
        _state["store"] = Store(_settings.database_url, _settings.dim)
    return _state["embedder"], _state["store"]


def get_answerer():
    if "answerer" not in _state:
        _state["answerer"] = make_answerer(_settings)
    return _state["answerer"]


def run_search(query: str) -> tuple[SearchResult, dict[str, str]]:
    try:
        embedder, store = get_engine()
        result = hybrid_search(store, embedder, query, _settings)
        titles = store.patent_titles([h.patent_id for h in result.hits])
    except RuntimeError as exc:  # for example a missing API key
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"search backend unavailable: {exc}") from exc
    return result, titles


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "embedder": _settings.embedder, "disclaimer": DISCLAIMER}


@app.post("/search")
def search(req: QueryRequest) -> dict:
    result, titles = run_search(req.query)
    return {
        "abstained": result.abstained,
        "best_similarity": result.best_similarity,
        "hits": [
            {
                "patent_id": h.patent_id,
                "title": titles.get(h.patent_id, ""),
                "score": h.score,
                "passages": [
                    {"id": c.chunk_id, "section": c.section, "position": c.position, "text": c.text}
                    for c in h.chunks
                ],
            }
            for h in result.hits
        ],
        "disclaimer": DISCLAIMER,
    }


@app.post("/answer")
def answer(req: QueryRequest) -> dict:
    result, titles = run_search(req.query)
    try:
        ans = answer_query(req.query, result, get_answerer())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    def item(i, verified: bool) -> dict:
        return {
            "patent_id": i.patent_id,
            "title": titles.get(i.patent_id, ""),
            "passage_id": i.passage_id,
            "excerpt": i.excerpt,
            "close": i.close,
            "different": i.different,
            "verified": verified,
        }

    return {
        "abstained": ans.abstained,
        "reliable": ans.reliable,
        "items": [item(i, True) for i in ans.items],
        "rejected": [item(i, False) for i in ans.rejected],
        "disclaimer": DISCLAIMER,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
