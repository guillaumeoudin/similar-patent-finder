"""Small web service: a search endpoint, an answer endpoint, and the web page.

Needs: pip install -e '.[api]'
Run with: uvicorn priorart.api:app

Locally there is no login and it should listen on 127.0.0.1 only. For a public deployment set
AUTH_REQUIRED=1 and SESSION_SECRET: every search and answer then needs an invite code and counts
against a request limit (see access.py).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from priorart.access import SESSION_SECONDS, AccessControl, make_session, read_session
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


COOKIE = "spf_session"
log = logging.getLogger("priorart")


class QueryRequest(BaseModel):
    query: str = Field(min_length=20, max_length=20000)


class LoginRequest(BaseModel):
    code: str = Field(min_length=4, max_length=200)


def answers_enabled() -> bool:
    """Cited answers need the Claude command line (local) or an API key (hosted)."""
    if _settings.answerer == "api":
        return bool(_settings.anthropic_api_key)
    return True


def get_access() -> AccessControl:
    if "access" not in _state:
        if not _settings.session_secret:
            raise HTTPException(status_code=503, detail="The server is not configured.")
        _state["access"] = AccessControl(
            _settings.database_url, _settings.rate_limit_per_hour, _settings.daily_cap
        )
    return _state["access"]


def guard(kind: str):
    """Dependency: when AUTH_REQUIRED is on, check the cookie, then count the request."""

    def check(request: Request, response: Response) -> None:
        if not _settings.auth_required:
            return
        if kind == "answer" and not answers_enabled():
            raise HTTPException(status_code=503, detail="Cited answers are not enabled here.")
        access = get_access()
        code_id = read_session(request.cookies.get(COOKIE), _settings.session_secret)
        if code_id is None or not access.is_active(code_id):
            raise HTTPException(status_code=401, detail="Please sign in with your access code.")
        quota = access.check_and_record(code_id, kind)
        if not quota.allowed:
            wait = max(quota.retry_after // 60, 1)
            detail = (
                "The daily limit for this demo is reached. Please try again tomorrow."
                if quota.reason == "daily"
                else f"Limit of {quota.limit} requests per hour reached. Try again in "
                f"about {wait} minutes."
            )
            raise HTTPException(
                status_code=429, detail=detail, headers={"Retry-After": str(quota.retry_after)}
            )
        request.state.code_id = code_id
        response.headers["X-Requests-Left"] = str(quota.remaining)
        response.headers["X-Requests-Limit"] = str(quota.limit)

    return check


def get_engine():
    """Create the embedder and the database connection on first use."""
    if "store" not in _state:
        _state["embedder"] = make_embedder(_settings)
        _state["store"] = Store(_settings.database_url, _settings.dim)
    return _state["embedder"], _state["store"]


def get_answerer():
    if "answerer" not in _state:
        _state["answerer"] = make_answerer(_settings)
    return _state["answerer"]


def run_search(query: str) -> tuple[SearchResult, dict[str, str]]:
    last: Exception | None = None
    for _attempt in (1, 2):
        try:
            embedder, store = get_engine()
            result = hybrid_search(store, embedder, query, _settings)
            titles = store.patent_titles([h.patent_id for h in result.hits])
            return result, titles
        except RuntimeError as exc:  # for example a missing API key
            log.error("search failed: %s", exc)
            raise HTTPException(status_code=503, detail=_public_error(exc)) from exc
        except Exception as exc:
            last = exc
            _state.pop("embedder", None)  # a serverless database may have dropped the connection
            _state.pop("store", None)
    log.error("search backend unavailable: %s", last)
    raise HTTPException(status_code=503, detail=_public_error(last))


def _refund(request: Request) -> None:
    """A request that failed on our side does not count against the visitor."""
    code_id = getattr(request.state, "code_id", None)
    if _settings.auth_required and code_id is not None:
        try:
            get_access().refund(code_id)
        except Exception as exc:  # the refund is a courtesy, never a reason to fail again
            log.error("refund failed: %s", exc)


def _public_error(exc: Exception | None) -> str:
    """Hosted: a generic message, so that no connection detail leaks. Local: the real cause."""
    if _settings.auth_required:
        return "The search service is temporarily unavailable."
    return f"search backend unavailable: {exc}"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "embedder": _settings.embedder, "disclaimer": DISCLAIMER}


@app.get("/config")
def config() -> dict:
    return {
        "auth_required": _settings.auth_required,
        "answers_enabled": answers_enabled(),
        "limit_per_hour": _settings.rate_limit_per_hour,
    }


@app.post("/login")
def login(req: LoginRequest, request: Request, response: Response) -> dict:
    if not _settings.auth_required:
        return {"ok": True}
    code_id = get_access().login(req.code)
    if code_id is None:
        time.sleep(0.7)  # slows down guessing
        raise HTTPException(status_code=401, detail="This access code is not valid.")
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        COOKIE,
        make_session(code_id, _settings.session_secret),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    return {"ok": True}


@app.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/me")
def me(request: Request) -> dict:
    if not _settings.auth_required:
        return {"signed_in": True, "left": None, "limit": None}
    access = get_access()
    code_id = read_session(request.cookies.get(COOKIE), _settings.session_secret)
    if code_id is None or not access.is_active(code_id):
        return {"signed_in": False}
    quota = access.usage(code_id)
    return {"signed_in": True, "left": quota.remaining, "limit": quota.limit}


@app.post("/search", dependencies=[Depends(guard("search"))])
def search(req: QueryRequest, request: Request) -> dict:
    try:
        result, titles = run_search(req.query)
    except HTTPException:
        _refund(request)
        raise
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


@app.post("/answer", dependencies=[Depends(guard("answer"))])
def answer(req: QueryRequest, request: Request) -> dict:
    try:
        result, titles = run_search(req.query)
        ans = answer_query(req.query, result, get_answerer())
    except HTTPException:
        _refund(request)
        raise
    except RuntimeError as exc:
        _refund(request)
        log.error("answer failed: %s", exc)
        raise HTTPException(status_code=503, detail=_public_error(exc)) from exc

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
