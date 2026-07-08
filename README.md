# Chatter

A simple social media web app: users register, post in Markdown, and comment on posts or on other comments with unlimited nesting.

## Requirements

- Docker and Docker Compose

## Setup

```sh
cp .env.example .env   # edit SECRET_KEY and Postgres credentials as needed
docker compose up
```

The app is served at [http://localhost:8000](http://localhost:8000). The container runs migrations automatically on startup.

## Development

- One-off management commands: `docker compose run --rm web python manage.py <command>`
- Adding a dependency: `uv add <package>` (updates `pyproject.toml` and `uv.lock`), then `docker compose build`
- Working outside Docker: `uv sync` creates a local `.venv/` from the same lockfile; without `POSTGRES_DB` set, the app falls back to SQLite

## Google sign-in

Registration and login also support "Continue with Google" alongside the regular username/password form. To enable it:

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one).
2. Go to **APIs & Services > OAuth consent screen** and configure it (External user type is fine for testing; add your own Google account as a test user while the app is unpublished).
3. Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID**, type **Web application**.
4. Add an **Authorized redirect URI** for each place you run the app, e.g.:
   - `http://localhost:8000/accounts/google/login/callback/` (Docker)
   - `http://localhost:8001/accounts/google/login/callback/` (uv/SQLite dev server)
5. Copy the generated Client ID and Client Secret into `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   ```
6. Restart the app. Without these set, the "Continue with Google" link still renders but Google will reject the request.

A Google-created account gets a `Profile` automatically, same as username/password registration, and lands in the same `User` table — there's no separate "social user" model to manage.

## Tests

```sh
docker compose run --rm web python manage.py test
```

## Build verification

```sh
./scripts/build-test.sh
```

Builds the image, brings up Postgres, runs migrations, runs the test suite, and runs `manage.py check --deploy`.
