"""The hosted mode of the web service: sign in, cookies, limits. No database, no network."""

import dataclasses

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from priorart import api  # noqa: E402
from priorart.access import Quota  # noqa: E402
from priorart.search import SearchResult  # noqa: E402

QUERY = "a charging pad with a coil that detects metal objects on its surface"


class FakeAccess:
    def __init__(self, limit=2):
        self.limit, self.used, self.revoked = limit, 0, False

    def visitor_id(self, key):
        return 1

    def login(self, code):
        return 1 if code == "good-code" else None

    def is_active(self, code_id):
        return code_id == 1 and not self.revoked

    def refund(self, code_id):
        self.used -= 1

    def usage(self, code_id):
        return Quota(self.used < self.limit, self.used, self.limit)

    def check_and_record(self, code_id, kind):
        if self.used >= self.limit:
            return Quota(False, self.used, self.limit, 600, "hourly")
        self.used += 1
        return Quota(True, self.used, self.limit)


@pytest.fixture()
def hosted(monkeypatch):
    settings = dataclasses.replace(api._settings, auth_required=True, session_secret="s" * 40)
    monkeypatch.setattr(api, "_settings", settings)
    monkeypatch.setattr(api, "_state", {"access": FakeAccess()})
    monkeypatch.setattr(api.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        api,
        "run_search",
        lambda q, c=None: (SearchResult(hits=[], best_similarity=0.9, abstained=False), {}),
    )
    return TestClient(api.app)


def test_search_needs_sign_in(hosted):
    assert hosted.post("/search", json={"query": QUERY}).status_code == 401
    assert hosted.get("/me").json() == {"signed_in": False}


def test_wrong_code_is_refused_and_right_code_signs_in(hosted):
    assert hosted.post("/login", json={"code": "bad-code"}).status_code == 401
    ok = hosted.post("/login", json={"code": "good-code"})
    assert ok.status_code == 200
    assert "httponly" in ok.headers["set-cookie"].lower()
    assert hosted.get("/me").json()["signed_in"] is True
    assert hosted.post("/search", json={"query": QUERY}).status_code == 200


def test_forged_cookie_is_refused(hosted):
    hosted.cookies.set(api.COOKIE, "1.9999999999.deadbeef")
    assert hosted.post("/search", json={"query": QUERY}).status_code == 401


def test_limit_returns_429_with_retry_after(hosted):
    hosted.post("/login", json={"code": "good-code"})
    first = hosted.post("/search", json={"query": QUERY})
    assert first.headers["x-requests-left"] == "1"
    assert hosted.post("/search", json={"query": QUERY}).status_code == 200
    blocked = hosted.post("/search", json={"query": QUERY})
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "600"
    # the message does not give the rule, and shows the visitor address
    assert blocked.json()["detail"]["message"] == "Rate limit reached."
    assert "ip" in blocked.json()["detail"]
    assert "hour" not in blocked.text and "2" not in blocked.json()["detail"]["message"]


def test_revoked_code_stops_working_at_once(hosted):
    hosted.post("/login", json={"code": "good-code"})
    api._state["access"].revoked = True
    assert hosted.post("/search", json={"query": QUERY}).status_code == 401


def test_answers_are_off_without_an_api_key(hosted, monkeypatch):
    settings = dataclasses.replace(api._settings, answerer="api", anthropic_api_key="")
    monkeypatch.setattr(api, "_settings", settings)
    hosted.post("/login", json={"code": "good-code"})
    assert hosted.get("/config").json()["answers_enabled"] is False
    assert hosted.post("/answer", json={"query": QUERY}).status_code == 503
    assert api._state["access"].used == 0  # a refused answer does not use up a request


def test_without_hosted_mode_nothing_changes(monkeypatch):
    settings = dataclasses.replace(api._settings, auth_required=False)
    monkeypatch.setattr(api, "_settings", settings)
    monkeypatch.setattr(
        api,
        "run_search",
        lambda q, c=None: (SearchResult(hits=[], best_similarity=0.9, abstained=False), {}),
    )
    assert TestClient(api.app).post("/search", json={"query": QUERY}).status_code == 200


def test_a_failed_search_is_refunded(hosted, monkeypatch):
    def broken(query, corpus=None):
        raise api.HTTPException(status_code=503, detail="down")

    monkeypatch.setattr(api, "run_search", broken)
    hosted.post("/login", json={"code": "good-code"})
    assert hosted.post("/search", json={"query": QUERY}).status_code == 503
    assert api._state["access"].used == 0


def test_public_mode_has_no_login_but_limits_each_visitor(monkeypatch):
    settings = dataclasses.replace(
        api._settings, auth_required=False, public_limits=True, session_secret="s" * 40
    )
    monkeypatch.setattr(api, "_settings", settings)
    monkeypatch.setattr(api, "_state", {"access": FakeAccess()})
    monkeypatch.setattr(
        api,
        "run_search",
        lambda q, c=None: (SearchResult(hits=[], best_similarity=0.9, abstained=False), {}),
    )
    client = TestClient(api.app)
    assert client.get("/me").json() == {"signed_in": True, "left": None, "limit": None}
    assert client.post("/search", json={"query": QUERY}).status_code == 200  # no sign in needed
    assert client.post("/search", json={"query": QUERY}).status_code == 200
    blocked = client.post("/search", json={"query": QUERY})
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "600"
