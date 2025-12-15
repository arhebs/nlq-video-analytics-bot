# Video Analytics NLQ Telegram Bot

Telegram bot (Python + aiogram) that answers Russian natural-language analytics questions over PostgreSQL.

Hard contract: **every incoming message must produce exactly one integer reply** (`^-?\\d+$`). On any unsupported input
or internal error, reply **`0`** (log internally).

## Setup

1) Create and activate a virtualenv (Python `3.12.x` recommended).

2) Install dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

3) Create `.env` from `.env.example` and fill `TELEGRAM_BOT_TOKEN`.

## Local Postgres (Docker)

```bash
docker compose up -d
```

Then ensure `DATABASE_URL` is set (see `.env.example`).

If you already have Postgres running on `localhost:5432`, run Compose on a different host port:

```bash
POSTGRES_HOST_PORT=5433 docker compose up -d
```

and update `DATABASE_URL` to use `5433`.

Optional readiness wait:

```bash
bash scripts/wait_for_db.sh
```

## Optional LLM parser (feature-flagged)

The default parser is rules-based and deterministic. If you enable the optional LLM parser, it must return **strict
Intent JSON** and is always validated (invalid output falls back to rules).

Set in `.env`:

- `LLM_ENABLED=true`
- `LLM_API_KEY=...`
- Optional: `LLM_MODEL`, `LLM_API_BASE`, `LLM_TIMEOUT_S`

## Migrations

```bash
python -m src.db.migrate
```

To drop and recreate tables (destructive):

```bash
python -m src.db.migrate --recreate
```

## Load dataset

```bash
python -m src.db.load_json --path videos.json --truncate
```

You can also load from a URL:

```bash
python -m src.db.load_json --url <dataset_url> --truncate
```

## Run bot (placeholder)

```bash
python -m src.bot.main
```

## Run tests (placeholder)

```bash
pytest -q
```
