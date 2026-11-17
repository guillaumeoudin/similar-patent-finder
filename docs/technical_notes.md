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
