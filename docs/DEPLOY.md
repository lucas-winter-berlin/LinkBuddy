# Deploy LinkBuddy on Railway

Persistent hosting so the bot runs without your PC.

## Why Postgres?

Railway’s filesystem is **ephemeral**. SQLite files vanish on redeploy.
Use Railway Postgres (or any `DATABASE_URL`). The app creates tables on boot.

## Option A — Dashboard (simplest)

### 1. Account

Open [railway.app](https://railway.app) → sign up (GitHub login works).

### 2. New project from GitHub

1. **New Project** → **Deploy from GitHub repo**
2. Select your `LinkBuddy` fork/repo
3. Railway detects Python / Nixpacks and uses `python main.py` (`railway.toml`)

### 3. Add Postgres

1. In the same project: **New** → **Database** → **PostgreSQL**
2. Open the bot service → **Variables**
3. Add a reference: `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`  
   (Railway UI: Variable → Add reference → Postgres → `DATABASE_URL`)

Railway’s Postgres URL is usually `postgresql://…`. LinkBuddy rewrites it to
`postgresql+asyncpg://…` automatically.

### 4. App variables

In the bot service → **Variables**, set at least:

| Name | Value |
|------|--------|
| `TELEGRAM_BOT_TOKEN` | from BotFather |
| `OWNER_USER_ID` | your Telegram user id |
| `GEMINI_API_KEY` | optional |
| `GEMINI_MODEL` | `gemini-flash-latest` (optional) |
| `BOT_TIMEZONE` | `Europe/Berlin` |
| `EXPORT_DAY` | `6` |
| `EXPORT_TIME` | `18:00` |
| `DEPLOYMENT_ENV` | `production` |
| `LOG_LEVEL` | `INFO` |

### 5. Deploy & verify

- Watch **Deployments** → logs until you see `Bot @… ist bereit`
- Message the bot on Telegram
- **Stop any local** `python main.py` (only one polling process per token)

### 6. Later updates

Push to `main` on GitHub → Railway redeploys automatically (if connected).

## Option B — CLI

```bash
npm i -g @railway/cli
railway login
cd LinkBuddy
railway init          # link or create project
railway add --database postgres
railway add --repo <you>/LinkBuddy --branch main --service linkbuddy
railway variable set TELEGRAM_BOT_TOKEN=... OWNER_USER_ID=... --service linkbuddy
# Wire DATABASE_URL as a reference to Postgres in the dashboard if needed
railway redeploy --service linkbuddy -y
```

## After go-live

| Check | |
|-------|--|
| Cloud logs show `Application started` | OK |
| Local bot process stopped | avoids `Conflict: getUpdates` |
| `/start` works on Telegram | OK |
| Save a link, then `/tags` | data in Postgres |

## Cost note

Railway has a free/trial credit tier; a small always-on bot + Postgres usually
stays cheap. Check [railway.app/pricing](https://railway.app/pricing).
