"""Command line: index the corpus, search it, and answer a question with checked citations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from priorart.answer import answer_query, make_answerer
from priorart.chunking import chunk_patent
from priorart.config import Settings, load_settings
from priorart.embeddings import estimate_tokens, make_embedder
from priorart.search import hybrid_search
from priorart.store import Store
from priorart.vectors import load_vectors, save_vectors

PATENTS_FILE = Path("data/processed/patents.jsonl")


def load_patents() -> list[dict]:
    with PATENTS_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def cmd_embed(settings: Settings, out: Path) -> None:
    """Compute the vectors for the whole corpus and save them in a folder (no database needed)."""
    patents = load_patents()
    chunks = [c for p in patents for c in chunk_patent(p)]
    embedder = make_embedder(settings)
    vectors: list[list[float]] = []
    batch = 128
    for i in range(0, len(chunks), batch):
        vectors.extend(embedder.embed([c.text for c in chunks[i : i + batch]]))
        print(f"  {min(i + batch, len(chunks))}/{len(chunks)}")
    save_vectors(out, [c.chunk_id for c in chunks], vectors, embedder.name)
    print(f"saved {len(chunks)} vectors from {embedder.name} to {out}")


def cmd_index(settings: Settings, confirmed: bool, reset: bool, vectors_dir: Path | None) -> None:
    patents = load_patents()
    chunks = [c for p in patents for c in chunk_patent(p)]
    tokens = estimate_tokens([c.text for c in chunks])
    print(f"{len(patents)} patents, {len(chunks)} chunks, about {tokens:,} tokens")

    if vectors_dir is not None:
        ids, vectors, meta = load_vectors(vectors_dir)
        if ids != [c.chunk_id for c in chunks]:
            raise SystemExit(
                "the vectors do not match the current chunks: run `priorart embed` again"
            )
        dim = meta["dim"]
        print(
            f"using saved vectors from {meta['model']} (dimension {dim}): nothing is sent anywhere"
        )
        embed_chunks = None
    else:
        dim = settings.dim
        embedder = make_embedder(settings)
        embed_chunks = embedder.embed
        if settings.embed_price_per_m_tokens:
            print(f"estimated cost: {tokens / 1e6 * settings.embed_price_per_m_tokens:.4f}")
        else:
            print("set EMBED_PRICE_PER_M_TOKENS to see a cost estimate")
        if not confirmed:
            print("nothing was sent. Re-run with --yes to embed and store.")
            return

    store = Store(settings.database_url, dim)
    if reset:
        store.reset()
    else:
        store.init_schema()
    for p in patents:
        store.add_patent(p)
    done = set() if reset else store.chunk_ids()
    todo = [i for i, c in enumerate(chunks) if c.chunk_id not in done]
    if done:
        print(f"{len(done)} chunks already stored, {len(todo)} left")
    batch = 256
    for first in range(0, len(todo), batch):
        idx = todo[first : first + batch]
        part = [chunks[i] for i in idx]
        if embed_chunks is None:
            vecs = [vectors[i] for i in idx]
        else:
            vecs = embed_chunks([c.text for c in part])
        store.add_chunks(part, vecs)
        print(f"  {min(first + batch, len(todo))}/{len(todo)}", flush=True)
    print(f"done. chunks in database: {store.count_chunks()}")


def cmd_search(settings: Settings, query: str) -> None:
    embedder = make_embedder(settings)
    store = Store(settings.database_url, settings.dim)
    result = hybrid_search(store, embedder, query, settings)
    if result.abstained:
        print(f"no document close enough (best similarity {result.best_similarity:.3f})")
        return
    titles = store.patent_titles([h.patent_id for h in result.hits])
    for rank, hit in enumerate(result.hits, start=1):
        print(f"{rank:2d}. {hit.patent_id}  score {hit.score:.4f}  {titles.get(hit.patent_id, '')}")
        top = hit.chunks[0]
        print(f"      [{top.section} {top.position}] {top.text[:160]}")


def cmd_answer(settings: Settings, query: str) -> None:
    embedder = make_embedder(settings)
    store = Store(settings.database_url, settings.dim)
    result = hybrid_search(store, embedder, query, settings)
    answer = answer_query(query, result, make_answerer(settings))
    if answer.abstained:
        print("no document close enough")
        return
    if not answer.reliable:
        print("WARNING: unreliable answer (invalid output or unverified excerpts)")
    for item in answer.items:
        print(f"\npatent {item.patent_id}  (verified excerpt from {item.passage_id})")
        print(f'  "{item.excerpt}"')
        print(f"  close: {item.close}")
        print(f"  different: {item.different}")
    for item in answer.rejected:
        print(f"\nREJECTED (excerpt not found in source): patent {item.patent_id}")
    print("\nThis is not legal advice.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="priorart")
    sub = parser.add_subparsers(dest="command", required=True)
    p_index = sub.add_parser("index", help="embed the corpus and store it")
    p_index.add_argument("--yes", action="store_true", help="confirm: send texts to the embedder")
    p_index.add_argument("--reset", action="store_true", help="drop and recreate the tables")
    p_index.add_argument("--vectors", type=Path, help="folder made by `priorart embed`")
    p_embed = sub.add_parser("embed", help="compute vectors for the corpus and save them")
    p_embed.add_argument("--out", type=Path, required=True, help="folder to write")
    for name in ("search", "answer"):
        p = sub.add_parser(name)
        p.add_argument("query", help="description of the invention")
    args = parser.parse_args()

    settings = load_settings()
    if args.command == "embed":
        cmd_embed(settings, args.out)
    elif args.command == "index":
        cmd_index(settings, args.yes, args.reset, args.vectors)
    elif args.command == "search":
        cmd_search(settings, args.query)
    else:
        cmd_answer(settings, args.query)


if __name__ == "__main__":
    main()
