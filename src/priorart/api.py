"""Small HTTP endpoint around the search. Needs: pip install -e '.[api]'.

Run with: uvicorn priorart.api:app
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from priorart.config import load_settings
from priorart.embeddings import make_embedder
from priorart.search import hybrid_search
from priorart.store import Store

app = FastAPI(title="Prior art search (demo, not legal advice)")
_settings = load_settings()
_state: dict = {}


class SearchRequest(BaseModel):
    query: str


def _deps():
    if not _state:
        _state["embedder"] = make_embedder(_settings)
        _state["store"] = Store(_settings.database_url, _settings.dim)
    return _state["embedder"], _state["store"]


@app.post("/search")
def search(req: SearchRequest) -> dict:
    embedder, store = _deps()
    result = hybrid_search(store, embedder, req.query, _settings)
    return {
        "abstained": result.abstained,
        "best_similarity": result.best_similarity,
        "hits": [
            {
                "patent_id": h.patent_id,
                "score": h.score,
                "passages": [
                    {"id": c.chunk_id, "section": c.section, "text": c.text} for c in h.chunks
                ],
            }
            for h in result.hits
        ],
        "disclaimer": "This is not legal advice.",
    }
