# LinkBuddy Architecture

This document describes how LinkBuddy is structured, how a Telegram update
flows through the system, and where to extend the codebase.

## 1. Goals

LinkBuddy is a **single-user Telegram bot** for saving, tagging, searching,
and exporting internet links (papers, code, videos, websites, …) with:

- Minimal input (paste / forward a URL)
- Conservative auto-tagging (heuristics + optional Gemini)
- Duplicate and broken-link handling
- Portable storage (SQLite locally, PostgreSQL in production)

Primary UI language: **German**. Code and architecture docs: **English**.

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram clients                        │
└────────────────────────────┬────────────────────────────────┘
                             │ long polling
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              python-telegram-bot Application                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Commands     │  │ Callbacks    │  │ Text / captions │  │
│  │ /suche …     │  │ Inline btns  │  │ → save / pending  │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬─────────┘  │
│         └─────────────────┼────────────────────┘            │
│                           ▼                                 │
│                    AppContext (bot_data)                    │
│              settings · Database · GeminiTagger             │
│                           │                                 │
│              ┌────────────┼────────────┐                    │
│              ▼            ▼            ▼                    │
│         services/      db/repo      icons (HTML)            │
│         URLs/tags      SQLAlchemy   Custom emoji            │
└──────────────┼────────────┼─────────────────────────────────┘
               │            │
               ▼            ▼
        HTTP (title)   SQLite / PostgreSQL
        Gemini API     (async engines)
```

The bot process is a long-running asyncio application started by `main.py`
(or `python -m linkbuddy`). There is **no HTTP webhook** in the MVP; Railway
and local setups both use **polling**.

## 3. Package layout

```
linkbuddy/
├── main.py                      # Thin entry for hosts (adds src/ to path)
├── pyproject.toml               # Package metadata + pytest config
├── requirements.txt             # Runtime deps
├── requirements-dev.txt         # pytest, …
├── railway.toml                 # Deploy start command
├── migrations/001_init.sql      # Reference schema for Postgres/Supabase
├── assets/
│   ├── emoji/*.webp             # Source icons for custom emoji pack
│   └── emoji_pack.json          # Uploaded custom_emoji_id map
├── scripts/
│   ├── generate_icons.py        # Render 100×100 Material-style WEBP icons
│   └── upload_emoji_pack.py     # createNewStickerSet + write emoji_pack.json
├── docs/                        # (this file lives at docs/ARCHITECTURE.md)
├── src/linkbuddy/
│   ├── config.py                # Settings from environment / .env
│   ├── icons.py                 # Custom emoji HTML + text fallbacks
│   ├── main.py                  # Logging, build Application, run_polling
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM (Resource, TagStat, …)
│   │   ├── engine.py            # Async engine + session helper
│   │   └── repository.py        # All reads/writes for one user
│   ├── services/
│   │   ├── urls.py              # Detect, normalise, validate, title extract
│   │   ├── tags.py              # Parse / normalise #tags
│   │   ├── tagging.py           # Heuristic suggestions
│   │   ├── gemini.py            # Optional Gemini tagger
│   │   ├── formatting.py        # Telegram HTML message builders
│   │   ├── export.py            # JSON / Markdown / CSV / Notion
│   │   └── periods.py           # Time windows in BOT_TIMEZONE
│   └── bot/
│       ├── app.py               # Handler wiring, auth, post_init
│       ├── context.py           # AppContext accessors, reply helpers
│       ├── state.py             # In-memory drafts / list views / pending
│       ├── keyboards.py         # Inline keyboards (+ icon_custom_emoji_id)
│       ├── jobs.py              # Weekly export JobQueue job
│       └── handlers/
│           ├── common.py        # /start /help /settings / errors
│           ├── router.py        # Free-text → pending input or new link
│           ├── save.py          # Save flow (validate → tag → confirm)
│           ├── query.py         # /suche /tag /tags /neue /heute …
│           ├── stats.py         # /stats /timeline /related /similar
│           └── manage.py        # /edit /delete /export + resource callbacks
└── tests/                       # pytest (asyncio), no live Telegram
```

### Layering rules

| Layer | May depend on | Must not |
|-------|---------------|----------|
| `bot/handlers` | `services`, `db`, `icons`, PTB | talk to Gemini/HTTP directly except via services |
| `services` | stdlib, HTTP, Gemini SDK | import `telegram` |
| `db` | SQLAlchemy | import `telegram` or Gemini |
| `config` / `icons` | stdlib / JSON assets | import handlers |

Keeping Telegram out of `services` and `db` makes the core logic testable
without a bot token.

## 4. Runtime bootstrap

1. `load_settings()` reads `.env` / process environment (`TELEGRAM_BOT_TOKEN`, …).
2. `Database(url)` constructs an async SQLAlchemy engine (no I/O yet).
3. `build_application(settings, database)` registers handlers and stores
   `AppContext` in `application.bot_data["app_context"]`.
4. On `post_init`:
   - `create_schema()` (`Base.metadata.create_all`)
   - `set_my_commands(…)`
   - schedule weekly export via `JobQueue`
5. `run_polling(drop_pending_updates=True)` starts the network loop.
6. On shutdown: `database.dispose()`.

**Important:** the engine is created in the same process/event loop that
runs the Application. Do not open DB connections in a separate `asyncio.run`
before polling — connection pools bind to the loop they were created on.

## 5. Data model

### 5.1 Tables

| Table | Role |
|-------|------|
| `resources` | One saved link (soft-deletable) |
| `resource_duplicates` | Optional link between original and “save separately” copy |
| `tag_stats` | Per-user tag counts + co-occurrence map |
| `export_logs` | Weekly / manual export audit trail |

### 5.2 `resources` (conceptual)

| Column | Notes |
|--------|--------|
| `user_id` | Telegram user id (always filtered) |
| `url` | Original URL as pasted |
| `url_hash` | SHA-256 of **normalised** URL (tracking params stripped) |
| `title` | From `og:title` / `<title>` / `h1` |
| `tags` | JSON array of strings (`ai/evals`, no leading `#`) |
| `tags_text` | Denormalised `\|ai/evals\|tools\|` for portable `LIKE` search |
| `notes` | Optional short note |
| `source` | `paper` \| `code` \| `video` \| `instagram` \| `website` |
| `status` | `active` \| `deleted` (soft delete) |
| `metadata` | JSON extras (`broken`, `ai_tagged`, …) mapped as ORM attr `meta` |

`url_hash` is **indexed but not UNIQUE**: the product allows storing a second
copy when the user chooses “Separat speichern”.

### 5.3 Portability (SQLite ↔ Postgres)

- JSON columns use `JSON().with_variant(JSONB(), "postgresql")`.
- No Postgres-only SQL in the repository (`ILIKE`, `jsonb_?`, `DATE_TRUNC`).
- Tag / full-text filters use `tags_text` + `LIKE` with escaped wildcards.
- Week timelines are aggregated in Python from fetched timestamps.

## 6. Request flows

### 6.1 Access control

Every command handler is registered with `filters.User(OWNER_USER_ID)` when
configured. Callback queries go through `_guarded()` which checks the same
owner. Unauthorised users get a short private-bot message.

Without `OWNER_USER_ID`, the bot is open (setup mode only).

### 6.2 Saving a link

```
Message with URL
      │
      ▼
router.text_router
      │  pending input? → apply tags/note/url edit
      ▼
save.handle_new_link
      │  extract URL, #tags, note
      ▼
Duplicate? ──yes──► inline: merge / copy / cancel
      │ no
      ▼
HTTP check ──broken──► inline: force save / edit URL / cancel
      │ ok
      ▼
extract_title + suggest_tags (heuristics ± Gemini)
      │
      ▼
Confirmation card (Speichern / Tags / Notiz / Abbrechen)
      │
      ▼
repository.create + tag_stats delta
```

Draft state lives in `context.user_data` under short tokens referenced from
`callback_data` (Telegram’s 64-byte limit). Drafts are process-local and lost
on restart — acceptable for in-flight dialogs.

### 6.3 Tag lists (`/tag`, `/tags`)

User-facing format is intentionally minimal:

```
#ai

- Title of link one
- Title of link two
```

`/tags` groups by root tag and lists all matching resources (including
children such as `#ai/evals`). Long messages are truncated with a hint to
use `/tag #name`.

### 6.4 Search & stats

- `/suche` — `LIKE` over URL, title, notes, `tags_text`
- `/stats`, `/top_tags`, `/timeline`, `/related`, `/similar` — repository
  aggregations + HTML formatting
- Period commands use `BOT_TIMEZONE` for “today” boundaries

### 6.5 Export

- Manual: `/export [#tag] [json|markdown|csv|notion]` → `send_document`
- Automatic: `JobQueue.run_daily` on configured weekday/time → JSON of the
  last 7 days

`EXPORT_DAY` in config uses Monday=0 … Sunday=6 (spec). PTB’s job queue uses
Sunday=0; `Settings.export_day_ptb` converts.

## 7. Auto-tagging pipeline

```
URL + title
    │
    ├─1─ Domain hints (arxiv → ai/research, github → tools, …)
    ├─2─ Word match against known user tags (stem-aware, min length 4)
    ├─3─ Co-occurrence boost from tag_stats
    └─4─ Gemini (optional)
            • if known_tags < 12 → may invent up to 2 new tags
            • else → only existing tags
```

Gemini failures time out / log a warning and degrade to heuristics. The
prompt forbids inventing tags when the collection is already rich.

## 8. Custom emoji / icons

1. `scripts/generate_icons.py` draws monochrome 100×100 WEBP icons.
2. `scripts/upload_emoji_pack.py` creates a Telegram `custom_emoji` sticker
   set with `needs_repainting=True` (icons follow text/theme colour).
3. IDs are stored in `assets/emoji_pack.json`.
4. `icons.html("search")` emits `<tg-emoji emoji-id="…">fallback</tg-emoji>`.
5. Inline buttons use `icon_custom_emoji_id` when available (Telegram requires
   Premium on the bot owner for icons on buttons in private chats); otherwise
   a text glyph prefix is used.

Never `html.escape()` a string that already contains `<tg-emoji>` — that was
the cause of visible raw HTML in early tag titles.

## 9. Configuration

See `.env.example` and the README table. Notable defaults:

| Key | Default |
|-----|---------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./linkbuddy.db` |
| `GEMINI_MODEL` | `gemini-flash-latest` |
| `BOT_TIMEZONE` | `Europe/Berlin` |
| `EXPORT_DAY` / `EXPORT_TIME` | Sunday / `18:00` |

`postgres://` and `postgresql://` DSNs are normalised to
`postgresql+asyncpg://`.

## 10. Security & privacy

- Single-user filter on every query path
- Secrets only in `.env` (gitignored); never commit tokens
- Soft delete keeps rows out of active search/stats
- Error handler logs stack traces server-side and sends a generic message
  to the user
- URLs are not written to INFO logs in handlers

## 11. Testing strategy

- `pytest` + `pytest-asyncio` (`asyncio_mode = auto`)
- In-memory / temp-file SQLite via fixtures in `tests/conftest.py`
- Unit coverage focuses on:
  - tag parsing / normalisation
  - URL normalisation & source detection
  - tagging heuristics + Gemini response parsing
  - repository CRUD, search, tag tree, soft delete, export builders
  - config loading

No live Telegram or Gemini calls in CI.

## 12. Deployment

| Environment | Mechanism |
|-------------|-----------|
| Local | `python main.py`, SQLite file |
| Railway | `railway.toml` → `python main.py`, set env vars; optional Postgres |
| Schema | Auto `create_all` on start; `migrations/001_init.sql` as reference |

Keep **one** polling process per bot token (multiple instances cause
`Conflict: terminated by other getUpdates`).

## 13. Extension points

| Want | Where |
|------|--------|
| New command | `bot/handlers/*` + register in `bot/app.py` |
| New source domain | `services/urls.py` `SOURCE_BY_DOMAIN` + `tagging.DOMAIN_TAG_HINTS` |
| Richer search | `db/repository.py` `search()` (consider FTS later) |
| Multi-user | Thread `user_id` already exists; add auth/onboarding |
| Webhook mode | Replace `run_polling` with PTB webhook setup |
| Notion sync | New service consuming `export` / repository list |

## 14. Glossary

| Term | Meaning |
|------|---------|
| Draft | In-memory pending save dialog (`state.Draft`) |
| Root tag | First segment of `ai/evals` → `ai` |
| `tags_text` | Pipe-wrapped denormalised tag string for SQL `LIKE` |
| Soft delete | `status='deleted'` + `deleted_at`; hidden from active queries |

---

*Last updated with the MVP that ships Gemini tagging, custom emoji icons,
and the simplified `/tags` list UI.*
