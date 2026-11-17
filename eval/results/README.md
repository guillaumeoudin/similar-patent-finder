# Result logs

Every evaluation run writes one JSON Lines file here. The first line is the configuration, then one line per query, and the last line is the summary. Times are UTC.

| File | Set | Search | Embedder | Answers |
|---|---|---|---|---|
| `run_dev_20261117T123807Z.jsonl` | dev | hybrid | multilingual-e5-small | no |
| `run_dev_20261117T131618Z.jsonl` | dev | hybrid | multilingual-e5-small | yes |
| `run_dev_20261117T135119Z.jsonl` | dev | hybrid | voyage-4-lite | no |
| `run_test_20261117T135529Z.jsonl` | test | hybrid | multilingual-e5-small | yes |
| `run_test_20261117T140402Z.jsonl` | test | hybrid | voyage-4-lite | yes |
| `run_test_20261117T141450Z.jsonl` | test | keyword | multilingual-e5-small | no |
| `run_test_20261117T141535Z.jsonl` | test | vector | multilingual-e5-small | no |
| `run_test_20261117T141608Z.jsonl` | test | vector | voyage-4-lite | no |
| `baseline_bm25_dev_20261117T120157Z.jsonl` | dev | BM25 in Python | none | no |
| `baseline_bm25_test_20261117T141438Z.jsonl` | test | BM25 in Python | none | no |

Tuning runs on the development set (`eval/tune.py`):

| File | Note |
|---|---|
| `tuning_dev_20261117T122531Z.json` | e5-small, first run. Made before the keyword ranking fix (query cut to 60 terms), kept for the record. Superseded. |
| `tuning_dev_20261117T123718Z.json` | e5-small, after the keyword fix. Superseded by the next file, which picks the threshold in the middle of the best range. |
| `tuning_dev_20261117T123751Z.json` | e5-small, final. Source of the settings used for the e5-small runs. |
| `tuning_dev_20261117T135113Z.json` | voyage-4-lite, final. Source of the settings used for the Voyage runs. |

The test set was run once per system, after the settings were frozen.
