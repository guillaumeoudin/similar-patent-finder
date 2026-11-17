"""Settings, read from environment variables (and an optional .env file).

No secret is ever written in the code. Copy .env.example to .env and fill it in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env reader: KEY=VALUE lines. Existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql://priorart:priorart@localhost:5432/priorart"
    # embeddings
    embedder: str = "local"  # "local", "voyage" or "mistral"
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    embed_model: str = "mistral-embed"
    embed_dim: int = 1024
    voyage_api_key: str = ""
    voyage_base_url: str = "https://api.voyageai.com/v1"
    voyage_model: str = "voyage-4-lite"
    voyage_dim: int = 1024
    voyage_rpm: int = 0  # requests per minute allowed by your account, 0 = no pacing
    voyage_tpm: int = 0  # tokens per minute allowed by your account, 0 = no pacing
    local_embed_model: str = "intfloat/multilingual-e5-small"
    local_embed_dim: int = 384
    embed_price_per_m_tokens: float = 0.0  # in your currency; set it to get a cost estimate
    # answers
    answerer: str = "claude-code"  # "claude-code" (your Claude subscription) or "api" (API key)
    anthropic_api_key: str = ""
    answer_model: str = "claude-sonnet-5-5"
    # search
    rrf_k: int = 60
    candidates: int = 50  # chunks fetched from each ranking before fusion
    top_k: int = 10  # patents returned
    abstain_below: float = 0.0  # minimum best cosine similarity, tuned on the dev set

    @property
    def dim(self) -> int:
        dims = {"local": self.local_embed_dim, "voyage": self.voyage_dim}
        return dims.get(self.embedder, self.embed_dim)


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def load_settings() -> Settings:
    load_dotenv()
    d = Settings()
    return Settings(
        database_url=os.environ.get("DATABASE_URL", d.database_url),
        embedder=os.environ.get("EMBEDDER", d.embedder),
        mistral_api_key=os.environ.get("MISTRAL_API_KEY", ""),
        mistral_base_url=os.environ.get("MISTRAL_BASE_URL", d.mistral_base_url),
        embed_model=os.environ.get("EMBED_MODEL", d.embed_model),
        embed_dim=_i("EMBED_DIM", d.embed_dim),
        voyage_api_key=os.environ.get("VOYAGE_API_KEY", ""),
        voyage_base_url=os.environ.get("VOYAGE_BASE_URL", d.voyage_base_url),
        voyage_model=os.environ.get("VOYAGE_MODEL", d.voyage_model),
        voyage_dim=_i("VOYAGE_DIM", d.voyage_dim),
        voyage_rpm=_i("VOYAGE_RPM", d.voyage_rpm),
        voyage_tpm=_i("VOYAGE_TPM", d.voyage_tpm),
        local_embed_model=os.environ.get("LOCAL_EMBED_MODEL", d.local_embed_model),
        local_embed_dim=_i("LOCAL_EMBED_DIM", d.local_embed_dim),
        embed_price_per_m_tokens=_f("EMBED_PRICE_PER_M_TOKENS", d.embed_price_per_m_tokens),
        answerer=os.environ.get("ANSWERER", d.answerer),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        answer_model=os.environ.get("ANSWER_MODEL", d.answer_model),
        rrf_k=_i("RRF_K", d.rrf_k),
        candidates=_i("CANDIDATES", d.candidates),
        top_k=_i("TOP_K", d.top_k),
        abstain_below=_f("ABSTAIN_BELOW", d.abstain_below),
    )
