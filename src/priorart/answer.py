"""Generate an answer with citations, and check every citation against the source.

The model must return, for each patent, an excerpt copied word for word from a passage it
was given. The code does not trust it: each excerpt is looked up in the passage text after
a light normalization (spaces, quote styles, case). An excerpt that is not found is
rejected, and the whole answer is flagged as unreliable.
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from priorart.config import Settings
from priorart.search import SearchResult

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
MIN_EXCERPT_CHARS = 15  # shorter excerpts prove nothing

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def normalize(text: str) -> str:
    """Lowercase, unify quote styles, collapse all whitespace. Used only for comparison."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip().casefold()


def verify_excerpt(excerpt: str, source: str) -> bool:
    """True if the excerpt appears in the source text, up to normalization."""
    e = normalize(excerpt)
    return len(e) >= MIN_EXCERPT_CHARS and e in normalize(source)


@dataclass
class Item:
    patent_id: str
    passage_id: str
    excerpt: str
    close: str
    different: str
    verified: bool = False


@dataclass
class Answer:
    items: list[Item] = field(default_factory=list)
    rejected: list[Item] = field(default_factory=list)
    reliable: bool = True
    abstained: bool = False
    raw: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class Answerer(Protocol):
    def generate(self, system: str, user: str) -> tuple[str, int, int]:
        """Return (text, input_tokens, output_tokens). Temperature must be 0."""
        ...


class ClaudeAnswerer:
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("ANSWERER=api needs: pip install -e '.[anthropic]'") from exc

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.answer_model

    def generate(self, system: str, user: str) -> tuple[str, int, int]:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text, msg.usage.input_tokens, msg.usage.output_tokens


class ClaudeCodeAnswerer:
    """Calls the `claude` command line tool, signed in with a Claude subscription.

    No API key and no API credit are needed. Limits of this mode: the command line tool does
    not let us set the temperature, so answers are not strictly repeatable, and usage counts
    against the subscription limits. Needs Claude Code installed and logged in.
    """

    def __init__(self, settings: Settings, timeout: int = 240):
        self._model = settings.answer_model
        self._timeout = timeout

    def generate(self, system: str, user: str) -> tuple[str, int, int]:
        cmd = [
            "claude", "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
            "--model", self._model, "--system-prompt", system,
        ]  # fmt: skip
        try:
            proc = subprocess.run(
                cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                timeout=self._timeout, check=False,
            )  # fmt: skip
        except FileNotFoundError as exc:
            raise RuntimeError("the `claude` command was not found: install Claude Code") from exc
        if proc.returncode != 0:
            raise RuntimeError(f"claude failed: {proc.stderr.strip()[:300]}")
        data = json.loads(proc.stdout)
        if data.get("is_error"):
            raise RuntimeError(f"claude returned an error: {str(data.get('result'))[:300]}")
        usage = data.get("usage", {})
        tokens_in = (
            usage.get("input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
        )
        return data["result"], tokens_in, usage.get("output_tokens", 0)


def make_answerer(settings: Settings) -> Answerer:
    if settings.answerer == "claude-code":
        return ClaudeCodeAnswerer(settings)
    if settings.answerer == "api":
        return ClaudeAnswerer(settings)
    raise ValueError(f"Unknown ANSWERER: {settings.answerer}")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def format_passages(result: SearchResult) -> tuple[str, dict[str, str]]:
    """Number the passages. Returns the prompt text and a map passage_id -> passage text."""
    lines: list[str] = []
    sources: dict[str, str] = {}
    for hit in result.hits:
        for chunk in hit.chunks:
            lines.append(
                f"[{chunk.chunk_id}] patent {chunk.patent_id}, {chunk.section} "
                f"{chunk.position or ''}:\n{chunk.text}\n"
            )
            sources[chunk.chunk_id] = chunk.text
    return "\n".join(lines), sources


def parse_items(raw: str) -> list[Item]:
    """Read the JSON object from the model output. Raises ValueError if it is not valid."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model output")
    data = json.loads(match.group(0))
    return [
        Item(
            patent_id=str(d["patent_id"]),
            passage_id=str(d["passage_id"]),
            excerpt=str(d["excerpt"]),
            close=str(d.get("close", "")),
            different=str(d.get("different", "")),
        )
        for d in data["items"]
    ]


def check_items(items: list[Item], sources: dict[str, str]) -> tuple[list[Item], list[Item]]:
    """Split items into verified and rejected. The cited passage must belong to the patent."""
    good, bad = [], []
    for item in items:
        source = sources.get(item.passage_id)
        ok = (
            source is not None
            and item.passage_id.startswith(item.patent_id + ":")
            and verify_excerpt(item.excerpt, source)
        )
        item.verified = ok
        (good if ok else bad).append(item)
    return good, bad


def answer_query(query: str, result: SearchResult, answerer: Answerer) -> Answer:
    if result.abstained or not result.hits:
        return Answer(abstained=True)
    passages, sources = format_passages(result)
    system = load_prompt("answer_v1_system.md")
    user = load_prompt("answer_v1_user.md").format(query=query, passages=passages)
    raw, tokens_in, tokens_out = answerer.generate(system, user)
    answer = Answer(raw=raw, input_tokens=tokens_in, output_tokens=tokens_out)
    try:
        items = parse_items(raw)
    except (ValueError, KeyError, TypeError):
        answer.reliable = False
        return answer
    answer.items, answer.rejected = check_items(items, sources)
    answer.reliable = not answer.rejected
    return answer
