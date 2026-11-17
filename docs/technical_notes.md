# Technical notes

Details that are useful to reproduce the work but would clutter the README.

## Settings used

- Hybrid search merges the two rankings with reciprocal rank fusion, constant k = 60, from 50 candidates per ranking.
- Up to 10 patents are returned, with a cap on chunks per patent.
- The keyword leg uses every term of the query (stop words removed) as an OR query and ranks with `ts_rank` and length normalization 1.
- Vectors are compared by cosine similarity with an HNSW index in pgvector.
- Chunks are one abstract per patent plus one chunk per claim, at most 2000 characters, longer text is split.

## Development set, 20 patents

These are the numbers I tuned on, so they are optimistic. "Recall" is the share of expected references found in the top 5 or top 10, and MRR is the mean reciprocal rank of the first expected reference.

| System | Embedder | Recall at 5 | Recall at 10 | MRR |
|---|---|---|---|---|
| Keywords only, BM25 | none | 0.41 | 0.49 | 0.68 |
| Keywords only, PostgreSQL | none | 0.41 | 0.45 | 0.73 |
| Vectors only | e5-small | 0.43 | 0.52 | 0.76 |
| Vectors only | voyage-4-lite | 0.43 | 0.48 | 0.71 |
| Hybrid (k = 60, 50 candidates) | e5-small | 0.40 | 0.47 | 0.80 |
| Hybrid (k = 60, 50 candidates) | voyage-4-lite | 0.42 | 0.50 | 0.76 |

One mistake worth telling. My first PostgreSQL keyword search cut the query to its first 60 terms and ranked with `ts_rank_cd`, and it reached only 0.35 recall at 10, well below the plain Python baseline. Using every term with `ts_rank` and length normalization brought it to 0.45.

## Declining to answer

The rule is on the best vector cosine similarity between the query and any chunk. The cutoff is the middle of the plateau that separates the development positives from ten off topic negatives.

| | e5-small | voyage-4-lite |
|---|---|---|
| Cutoff (cosine similarity) | 0.862 | 0.569 |

The e5 similarities all sit between 0.80 and 0.97 on the development set, so its cutoff rests on a gap of 0.06. Voyage spreads them wider, with a gap of 0.21. The last ten negatives (other electrical devices) were never used for tuning.

## Cited answers

The answer step ran on the hybrid search of both models, through a Claude subscription (`ANSWERER=claude-code`). Quotes are verified after normalizing spaces and quote styles. The command line mode cannot set the temperature.

## Cost and speed

Search takes 0.38 s per query with the local model and 1.1 s with Voyage, network call included. The collection is about 960,000 tokens and the voyage-4-lite model includes 200 million free tokens. The answer step takes 10.2 s per query with e5-small and 11.5 s with Voyage, search included.

## Candidate depth

The development numbers hinted that 100 candidates per ranking helped Voyage a little. I kept 50 for both models and did not re-tune after seeing the test set.

## Cited answers, full table

| | With e5-small | With voyage-4-lite |
|---|---|---|
| Quotes the model gave | 101 | 125 |
| Quotes found word for word in the patent | 100 | 124 |
| Answers flagged unreliable | 1 of 50 | 1 of 50 |
| Patents where the model gave no quote at all | 7 | 2 |
| Time for search plus answer | about 10 s | about 11 s |

In each run one quote was not found. The program dropped it and flagged the answer. I did not look into why the model produced it. I read the comments themselves by hand on one example only.

## Declining to answer, full table

| | With e5-small | With voyage-4-lite |
|---|---|---|
| Real test patents wrongly declined | 0 of 50 | 0 of 50 |
| Unrelated descriptions correctly declined | 10 of 10 | 9 of 10 |

20 descriptions of things not in the collection were written. The first ten, plainly off topic, set the cutoff. The other ten (wired charging, solar inverters and similar) were kept aside only to be reported.

## Keyword search

BM25 is a refinement of TF-IDF: it weighs a word by how often it appears in a document and how rare it is across the collection, with a correction for document length. The database search uses PostgreSQL full text search with `ts_rank`, which looks at term frequency but does not weigh rare words.

## Running it, details

- The embedding model is chosen with `EMBEDDER` in `.env`. `local` runs an open model on your machine, needs no key and is the default. `voyage` and `mistral` call a web service and need a key. The open model and Voyage are measured. Mistral is implemented but was never run, because its free plan no longer gives API access.
- A Voyage account without a payment method is limited to 3 requests and 10,000 tokens a minute, too little to index the collection at a normal pace. `VOYAGE_RPM` and `VOYAGE_TPM` make the code slow down to fit.
- `priorart index` alone prints the size and a cost estimate and sends nothing.
- The answer step can use a Claude subscription through the `claude` command line tool (`ANSWERER=claude-code`, the default), or an API key (`ANSWERER=api`, needs `pip install -e ".[anthropic]"`). The command line mode cannot set the temperature, so two runs can differ.
- The web page listens on the local machine only, at http://127.0.0.1:8000. Embeddings can also be computed on another machine and copied over, see `docs/gpu_machine.md`.
- Tests and the development evaluation: `ruff check .`, `pytest -q` (80 tests, the ones that need the database are skipped when it is not running), `python eval/run_eval.py --set dev`.

## Repository layout

`src/priorart`: `ingest.py` and `chunking.py` prepare texts, `embeddings.py` and `store.py` handle the numbers and PostgreSQL, `search.py` merges rankings, `answer.py` writes the answer and checks every quote, `cli.py` and `api.py` are the entry points, `corpora.py` and `corpora.json` list the corpora, `access.py` holds the request limits and the invite codes, `static/` is the web page. `eval/` has the evaluation scripts and every log in `eval/results/`. `corpora/` has the selection script and the patent numbers of the coffee corpus. `prompts/` holds the prompts as text files. `docs/` has these notes, the deployment guide and the GPU machine note. `app.py`, `vercel.json`, `requirements.txt` and `.vercelignore` are for the Vercel deployment.

## The coffee collection (illustration only)

450 patents drawn at random (seed 7) from the 3,463 granted 2015 to 2025 in CPC group A47J31, 7,675 chunks, embedded with voyage-4-lite. It has no examiner based answer key and is not part of the evaluation.

Its abstention cutoff (0.563) comes from 8 hand written descriptions of the field and 8 off topic ones: the lowest in-field best similarity was 0.593 and the highest off topic one 0.533, so the margin is narrow (0.06).

## Ranking on the web page

Results are ranked by reciprocal rank fusion of the semantic and the keyword rankings of the passages (constant 60, 50 candidates from each). The similarity shown on each patent is the best cosine similarity among the passages displayed for it, computed in one extra query that changes no ranking. The abstention cutoff applies to the best vector similarity found. Search and ranking are the same as in the evaluation, only the display is added.
