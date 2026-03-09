# paid-art-cdn

A FastAPI server that gates file access behind Patreon membership. Users authenticate via Patreon OAuth; only active patrons in the configured tier(s) can view or download files.

## Setup

1. Create a `.env` file:

```env
PATREON_CLIENT_ID=...
PATREON_CLIENT_SECRET=...
PATREON_REDIRECT_URI=https://yourdomain.com/auth/callback
PATREON_CAMPAIGN_ID=...
PAID_TIER=Gold                  # comma-separated tier titles
SECRET_KEY=random-secret
FILES_DIR=./files               # directory of protected files
COOKIE_SECURE=true              # set false for local dev (HTTP)
RATE_LIMIT_PER_MINUTE=60
```

2. Install and run:

```bash
uv sync
uv run paid-art-cdn
```

Server listens on port `4444`.

## How it works

- `/auth/login` — redirects to Patreon OAuth
- `/auth/callback` — exchanges code for token, stores session
- `/access/{file_name}` — shows viewer page (auth-gated)
- `/stream/{file_name}` — serves raw file bytes (auth-gated)

Files are served only to active patrons whose tier matches `PAID_TIER`. All others get a 403 page.
