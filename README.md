# LinkBuddy

Personal Telegram bot for saving, tagging, searching, and exporting links
(arXiv, GitHub, Instagram, websites, …) with minimal input and conservative
auto-tagging.

**Single-user · German UI · Python 3.11+**

Architecture deep-dive: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

## Features

- Save links by pasting or forwarding (optional `#tags` + short note)
- Auto-tagging: domain/word heuristics + optional [Gemini](https://ai.google.dev/)
- Duplicate detection (merge / save separately / cancel)
- Broken-link warning with “save anyway”
- Search & browse: `/search`, `/tag`, `/tags`, `/latest`, `/today`, `/week`, `/month`
- Stats: `/stats`, `/top_tags`, `/timeline`, `/related`, `/similar`
- Manage: `/edit`, `/delete`, `/export` (`json` · `markdown` · `csv` · `notion`)
- Weekly JSON export via JobQueue (default: Sunday 18:00 `Europe/Berlin`)
- Custom emoji icon pack (Material-style, theme-aware)

## Tech stack

| Piece | Choice |
|-------|--------|
| Bot | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) 22.x |
| DB | SQLAlchemy 2 async — SQLite locally, PostgreSQL/Supabase in production |
| AI | Google Gemini (`google-genai`), optional |
| Deploy | Railway / Render / any long-running Python host |

## Quick start

### 1. Create a bot

Talk to [@BotFather](https://t.me/BotFather), copy the token, open a chat with
your bot, and look up your Telegram user id (e.g. via [@userinfobot](https://t.me/userinfobot)).

### 2. Install

```bash
git clone https://github.com/<you>/LinkBuddy.git
cd LinkBuddy
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
OWNER_USER_ID=...
# optional
# GEMINI_API_KEY=...
# DATABASE_URL=postgresql://...
```

Without `OWNER_USER_ID` the bot answers everyone (setup only). `/start` prints
your user id.

### 3. Run

```bash
python main.py
```

SQLite creates `linkbuddy.db` in the project root by default.

### 4. Save a link

```
https://arxiv.org/abs/2401.12345 #ai/evals Nice paper!
```

## Commands cheat sheet

| Command | Purpose |
|---------|---------|
| `/search …` | Full-text search |
| `/tag #ai` | Links under one tag (incl. children) |
| `/tags` | All tags with links as a simple list |
| `/latest [N]` | Latest links |
| `/today` | Saved today |
| `/week` | Last 7 days |
| `/month` | Last 30 days |
| `/stats` | Overview |
| `/export` | Download collection |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Custom emoji pack (optional)

Only needed if you want your own Telegram custom emoji pack (forks /
rebrand). The shipped IDs in `assets/emoji_pack.json` belong to the
original bot; regenerate for yours:

```bash
python scripts/generate_icons.py
python scripts/upload_emoji_pack.py
```

Requires a running bot token and `OWNER_USER_ID`. Button icons need
Telegram Premium on the bot owner; message icons work for everyone.

## Deploy (Railway)

See **[docs/DEPLOY.md](docs/DEPLOY.md)** for the full walkthrough (GitHub → Railway + Postgres).

Short version: connect the GitHub repo on [railway.app](https://railway.app), add
Postgres, set `TELEGRAM_BOT_TOKEN` / `OWNER_USER_ID` / `DATABASE_URL`, deploy,
then **stop the local bot**.

**Run only one polling process per token.**

## Environment variables

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | yes | — | BotFather token |
| `OWNER_USER_ID` | recommended | open | Only this Telegram user may use the bot |
| `DATABASE_URL` | no | local SQLite | `sqlite+…` or `postgresql://…` |
| `GEMINI_API_KEY` | no | — | Enables Gemini tagging |
| `GEMINI_MODEL` | no | `gemini-flash-latest` | Model id |
| `BOT_TIMEZONE` | no | `Europe/Berlin` | Day boundaries & export |
| `EXPORT_DAY` | no | `6` | 0=Mon … 6=Sun |
| `EXPORT_TIME` | no | `18:00` | Weekly export time |
| `LOG_LEVEL` | no | `INFO` | Logging level |

## Project layout

```
├── docs/
│   ├── ARCHITECTURE.md      # System design
│   └── DEPLOY.md            # Railway + Postgres
├── src/linkbuddy/           # Application package
│   ├── bot/                 # Telegram handlers & jobs
│   ├── db/                  # Models + repository
│   ├── services/            # Domain logic (no Telegram imports)
│   ├── config.py
│   └── icons.py
├── scripts/                 # Optional: regenerate/upload emoji pack
├── assets/                  # Emoji WEBP + pack JSON (for custom pack setup)
├── migrations/              # Postgres reference SQL
├── railway.toml             # Production start command
└── tests/
```

## License

MIT — see [LICENSE](LICENSE).
