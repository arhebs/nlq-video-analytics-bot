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

3) Create `.env` from `.env.example` and fill at least:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`

## Create a bot token (BotFather)

1) Open `@BotFather` in Telegram.
2) Run `/newbot` and follow the prompts.
3) Copy the token and set it as `TELEGRAM_BOT_TOKEN` in your `.env`.

Notes:

- Bot name (display) can be anything (e.g. “Video Analytics Bot”).
- Username must be unique and end with `bot` (e.g. `nlq_video_analytics_bot`).

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

## Run bot

```bash
python -m src.bot.main
```

## Run tests

```bash
pytest -q
```

## Deployment

### Option A: Docker (recommended)

Build the image:

```bash
docker build -t nlq-video-analytics-bot .
```

Run the bot container (pass env vars; do not bake secrets into the image):

```bash
docker run -d --name nlq-video-analytics-bot --env-file .env nlq-video-analytics-bot
```

If Postgres is on the host machine, ensure `DATABASE_URL` uses an address reachable from the container
(for example, on Linux you can use `host.docker.internal` if configured, or run the container with
`--network host`).

### Option B: systemd (VPS)

1) Copy the repo to the server (e.g. `/opt/nlq-video-analytics-bot`).
2) Create a virtualenv and install deps.
3) Create `/opt/nlq-video-analytics-bot/.env` with required env vars.
4) Install the provided service file from `deploy/systemd/nlq-video-analytics-bot.service:1`,
   adjust paths/user, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nlq-video-analytics-bot
sudo journalctl -u nlq-video-analytics-bot -f
```

## Required environment variables

- `TELEGRAM_BOT_TOKEN` (required)
- `DATABASE_URL` (required)
- `DB_TIMEZONE=UTC` (required; validated at startup)

Optional:

- `LOG_LEVEL` (default `INFO`)
- `LLM_ENABLED` / `LLM_API_KEY` / `LLM_MODEL` / `LLM_API_BASE` / `LLM_TIMEOUT_S`

## Checker readiness

- The bot must be running on a machine reachable by Telegram (public internet).
- Apply migrations and load the dataset once before starting the bot.
- Bot replies are always digits-only; `/start` also replies `0` by design.
- Use `@rlt_test_checker_bot` and follow its `/check` instructions for your repository and bot username.
