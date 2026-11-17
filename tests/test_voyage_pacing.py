import httpx

from priorart.config import Settings
from priorart.embeddings import VoyageEmbedder


class FakeResponse:
    status_code = 200
    headers: dict = {}

    def __init__(self, n):
        self.n = n

    def json(self):
        data = [{"index": i, "embedding": [float(i)]} for i in range(self.n)]
        return {"data": data, "usage": {"total_tokens": self.n}}

    def raise_for_status(self):
        return None


def test_voyage_splits_by_size_and_paces_requests(monkeypatch):
    sent = []
    sleeps = []
    clock = {"t": 0.0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            sent.append(len(json["input"]))
            return FakeResponse(len(json["input"]))

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds

    monkeypatch.setattr(httpx, "Client", FakeClient)
    emb = VoyageEmbedder(Settings(voyage_api_key="k", voyage_rpm=3, voyage_tpm=1000))
    emb._sleep, emb._now = fake_sleep, lambda: clock["t"]
    out = emb.embed(["x" * 400] * 30)  # about 100 tokens each, 3000 in all
    assert len(out) == 30
    assert max(sent) <= 8  # a request stays under 70 percent of the per minute budget
    assert sum(sent) == 30 and len(sent) > 3
    assert sleeps  # the per minute limits forced at least one wait


def test_voyage_without_limits_sends_few_large_requests(monkeypatch):
    sent = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            sent.append(len(json["input"]))
            return FakeResponse(len(json["input"]))

    monkeypatch.setattr(httpx, "Client", FakeClient)
    emb = VoyageEmbedder(Settings(voyage_api_key="k"))
    assert len(emb.embed(["short text"] * 200)) == 200
    assert sent == [128, 72]
