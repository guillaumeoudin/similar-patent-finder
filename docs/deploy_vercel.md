# Hosting the web page on Vercel

The page and its API can run on Vercel, with the data in a Neon PostgreSQL database. This is optional: the project works the same on your own machine.

## What runs where

| Part | Where |
|---|---|
| Web page and API (`app.py`, FastAPI) | Vercel function |
| Patent texts and vectors | Neon (PostgreSQL with pgvector) |
| Embeddings of the query | Voyage API (`voyage-4-lite`) |
| Cited answers (optional) | Anthropic API |

The open local embedding model cannot run on Vercel (too large), so the hosted version uses Voyage. The vectors in the database must come from the same model, 1024 dimensions.

## Why there is a login

Every search calls a paid service, and every cited answer calls a paid language model. A public page with no gate would let anyone spend your credit. So when `AUTH_REQUIRED=1`:

- Each person gets an **invite code**. You create and revoke them yourself. Only a hash of each code is stored.
- Signing in gives a signed cookie that cannot be forged. Revoking a code stops it at once.
- A code may make `RATE_LIMIT_PER_HOUR` requests per rolling hour (10 by default), and all codes together may make `DAILY_CAP` per day (200 by default). A request that fails on the server side is not counted.
- Cited answers are available only if `ANSWERER=api` and `ANTHROPIC_API_KEY` is set. Without a key, the page shows search only.

The limits protect you against a leaked code. For a hard ceiling, also set a monthly spending limit in the Voyage and Anthropic consoles.

## Steps

1. Create a Neon project and copy its **pooled** connection string.
2. Load the data. With vectors already computed in a local database, copy the `patents` and `chunks` tables to Neon. Or run `priorart embed --out data/vectors/voyage` with `EMBEDDER=voyage`, then `priorart index --vectors data/vectors/voyage --yes` with `DATABASE_URL` pointing at Neon.
3. Create invite codes against the Neon database: `DATABASE_URL=... priorart codes create --label "name"`. The code is shown once. `priorart codes list` and `priorart codes revoke --id N` manage them.
4. Set these variables on the Vercel project (Production and Preview):

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon pooled connection string |
| `EMBEDDER` | `voyage` |
| `VOYAGE_API_KEY` | your Voyage key |
| `VOYAGE_MODEL`, `VOYAGE_DIM` | `voyage-4-lite`, `1024` |
| `ABSTAIN_BELOW` | `0.5693` (tuned for this model, see `docs/technical_notes.md`) |
| `AUTH_REQUIRED` | `1` |
| `SESSION_SECRET` | a long random string |
| `ANSWERER` | `api` |
| `ANTHROPIC_API_KEY` | optional, enables cited answers |

5. Deploy with `vercel deploy`, check the preview, then `vercel deploy --prod`.

Never put these values in the repository. `.env*` files are ignored, and `.vercelignore` keeps data and local files out of the upload.
