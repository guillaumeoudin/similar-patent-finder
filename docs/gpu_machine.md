# Computing embeddings on another machine (open model)

The open embedding model can run on a stronger machine than the one that hosts the database. That machine only computes vectors and writes them to a folder. The folder is copied back and loaded into the database. No database and no API key are needed on the strong machine.

## On the strong machine

1. Copy these to the machine: the repository, and the file `data/processed/patents.jsonl` (made by `python -m priorart.ingest`).
2. Create an environment and install the local extra:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[local]"
```

3. For a GPU, install the PyTorch build that matches the card (NVIDIA CUDA or AMD ROCm) by following the instructions on the PyTorch website. Without it the model runs on the CPU, which also works but is slower.
4. Pick the model in the environment and run:

```bash
export EMBEDDER=local
export LOCAL_EMBED_MODEL=BAAI/bge-m3
export LOCAL_EMBED_DIM=1024
priorart embed --out data/vectors/bge-m3
```

The model is downloaded from the model hub on the first run. A smaller model also works, for example `intfloat/multilingual-e5-small` with `LOCAL_EMBED_DIM=384`.

## Back on the database machine

Copy the folder `data/vectors/bge-m3` into the same place, then:

```bash
export EMBEDDER=local LOCAL_EMBED_MODEL=BAAI/bge-m3 LOCAL_EMBED_DIM=1024
priorart index --vectors data/vectors/bge-m3 --reset
```

Search queries are embedded on the database machine with the same model, so that machine also needs `pip install -e ".[local]"`. A single query is cheap, even on a CPU.

## Rules to keep results comparable

- One vector folder per model. Never mix vectors from two models in one database.
- `--reset` empties the tables before loading.
- The folder records the model name and dimension. `priorart index` checks that the vectors match the current chunks and refuses otherwise.
