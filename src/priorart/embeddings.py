"""Embedders: turn text into vectors.

`Embedder` is the interface. Two backends exist: Mistral through its HTTP API, and a
local open model (sentence-transformers). Which one is used is a configuration choice
(EMBEDDER=mistral or EMBEDDER=local). Nothing else in the code knows which one runs.
"""

from __future__ import annotations

import time
from typing import Protocol

from priorart.config import Settings


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        """Return one vector per text, in the same order.

        kind is "document" for stored passages and "query" for a search text. Some models
        need to know which one it is. Others ignore it.
        """
        ...


def estimate_tokens(texts: list[str]) -> int:
    """Rough token count (about 4 characters per token). Used only for cost estimates."""
    return sum(len(t) for t in texts) // 4


def e5_prefix(model_name: str, kind: str) -> str:
    """E5 models were trained with 'query: ' and 'passage: ' prefixes. Other models need none."""
    if "e5" not in model_name.lower():
        return ""
    return "query: " if kind == "query" else "passage: "


class MistralEmbedder:
    def __init__(self, settings: Settings, batch_size: int = 32):
        if not settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY is not set")
        self.name = settings.embed_model
        self.dim = settings.embed_dim
        self._url = settings.mistral_base_url.rstrip("/") + "/embeddings"
        self._key = settings.mistral_api_key
        self._batch = batch_size
        self.tokens_used = 0

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        import httpx

        vectors: list[list[float]] = []
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(texts), self._batch):
                batch = texts[i : i + self._batch]
                resp = client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"model": self.name, "input": batch},
                )
                resp.raise_for_status()
                body = resp.json()
                self.tokens_used += body.get("usage", {}).get("total_tokens", 0)
                data = sorted(body["data"], key=lambda d: d["index"])
                vectors.extend(d["embedding"] for d in data)
        return vectors


class VoyageEmbedder:
    """Voyage AI through its HTTP API. Retries when the service says "too many requests"."""

    def __init__(self, settings: Settings, batch_size: int = 64, max_retries: int = 8):
        if not settings.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY is not set")
        self.name = settings.voyage_model
        self.dim = settings.voyage_dim
        self._url = settings.voyage_base_url.rstrip("/") + "/embeddings"
        self._key = settings.voyage_api_key
        self._batch = batch_size
        self._max_retries = max_retries
        self._sleep = time.sleep
        self.tokens_used = 0

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        import httpx

        input_type = "query" if kind == "query" else "document"
        vectors: list[list[float]] = []
        with httpx.Client(timeout=120) as client:
            for i in range(0, len(texts), self._batch):
                body = {"model": self.name, "input": texts[i : i + self._batch],
                        "input_type": input_type, "output_dimension": self.dim}  # fmt: skip
                for attempt in range(self._max_retries):
                    resp = client.post(
                        self._url, headers={"Authorization": f"Bearer {self._key}"}, json=body
                    )
                    if resp.status_code == 429:
                        wait = float(resp.headers.get("retry-after", 5 * 2**attempt))
                        self._sleep(min(wait, 65))
                        continue
                    resp.raise_for_status()
                    break
                else:
                    raise RuntimeError("Voyage kept answering 'too many requests'")
                data = resp.json()
                self.tokens_used += data.get("usage", {}).get("total_tokens", 0)
                vectors.extend(
                    d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])
                )
        return vectors


class LocalEmbedder:
    """Open model run on this machine. Needs: pip install -e '.[local]'."""

    def __init__(self, settings: Settings):
        from sentence_transformers import SentenceTransformer

        self.name = settings.local_embed_model
        self.dim = settings.local_embed_dim
        self._model = SentenceTransformer(self.name)
        self.tokens_used = 0

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        prefix = e5_prefix(self.name, kind)
        texts = [prefix + t for t in texts]
        vectors = self._model.encode(
            texts, normalize_embeddings=True, batch_size=32, show_progress_bar=len(texts) > 64
        )
        return vectors.tolist()


def make_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "mistral":
        return MistralEmbedder(settings)
    if settings.embedder == "voyage":
        return VoyageEmbedder(settings)
    if settings.embedder == "local":
        return LocalEmbedder(settings)
    raise ValueError(f"Unknown EMBEDDER: {settings.embedder}")
