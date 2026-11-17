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

## Who can use it, and the limits

Every search calls a paid service, and every cited answer calls a paid language model. A public page with no gate would let anyone spend your credit, so there are two ways to protect it:

- **Invite codes** (`AUTH_REQUIRED=1`). Each person gets a code that you create and revoke yourself. Only a hash of each code is stored. Signing in gives a signed cookie that cannot be forged.
- **Per visitor limits without login** (`AUTH_REQUIRED=0`, `PUBLIC_LIMITS=1`). The visitor is recognized by a salted hash of the address, which is never stored.

In both modes the same limits apply, per visitor and per rolling hour. Every request uses the embedding service, so all requests count against `RATE_LIMIT_PER_HOUR` (10 by default). Only cited answers use the AI model, so only they count against `ANTHROPIC_RATE_LIMIT_PER_HOUR` (10 by default). All visitors together may make `DAILY_CAP` requests per day (200 by default). A request that fails on the server side is not counted.

When a limit is reached the page only says that the rate limit is reached and shows the visitor's address. It does not say what the rule is.

Cited answers are available only if `ANSWERER=api` and `ANTHROPIC_API_KEY` is set. Without a key, the page shows search only.

The limits protect you against a leaked code or a curious crowd. For a hard ceiling, also set a monthly spending limit in the Voyage and Anthropic consoles.

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
| `AUTH_REQUIRED` | `1` for invite codes, `0` for open access |
| `PUBLIC_LIMITS` | `1` to limit each visitor when there is no login |
| `SESSION_SECRET` | a long random string |
| `ANSWERER` | `api` |
| `ANTHROPIC_API_KEY` | optional, enables cited answers |

5. Link the project with `vercel link`, then deploy with `vercel deploy --prod`. The `.vercelignore` file leaves out `pyproject.toml` on purpose, so that Vercel reads `requirements.txt`.
6. Vercel turns on its own sign in wall for new projects. To let visitors in with no Vercel account, turn off Deployment Protection in the project settings.

Never put these values in the repository. `.env*` files are ignored, and `.vercelignore` keeps data and local files out of the upload.
