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

## Email verification

Registering with username/password sends a verification link and does **not** log you in immediately — logging in is blocked until you click it. Google sign-in skips this, since Google already verified that email for you.

In dev (no `EMAIL_HOST` set in `.env`), verification emails aren't actually sent — they print to the `runserver`/`docker compose logs web` console instead (`EMAIL_BACKEND` falls back to Django's console backend). Grab the verification link from there. Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in `.env` to send real emails via SMTP. Links expire after 3 days (`EMAIL_VERIFICATION_MAX_AGE` in settings); an expired or invalid link offers a resend option.

Accounts that existed before this feature was added (created via `docker compose exec web python manage.py createsuperuser`, direct DB access, etc.) are grandfathered in as verified by a data migration — only new registrations go through the gate.

## Profiles

Users can set a bio and avatar image at `/settings/profile/`, and follow/unfollow other users from their profile page. Profiles show recent posts, recent comments, and post/comment/follower/following counts.

Avatars are stored on local disk under `media/` (gitignored) and served directly by Django in dev. That's fine for a single-container demo but won't survive a redeploy or scale past one instance — swapping in S3-compatible storage (e.g. `django-storages`) is the drop-in fix if this goes further. Max upload size is capped at 2MB (`MAX_AVATAR_UPLOAD_SIZE` in settings).

## Styling

Styling uses [Tailwind CSS](https://tailwindcss.com) via the standalone CLI binary — no Node.js/npm anywhere in the stack. Source is `static/css/input.css`; compiled output is `static/css/tailwind.css` (gitignored, generated).

Inside Docker this happens automatically: the Dockerfile downloads a pinned CLI binary and compiles the CSS at image build time, and `docker-entrypoint.sh` runs it in `--watch` mode alongside `runserver` when `DEBUG=1`, so editing a template's classes rebuilds the CSS live.

Outside Docker (the `uv`/SQLite workflow), fetch the CLI once and run it in watch mode yourself alongside `manage.py runserver`:

```sh
curl -fsSL -o bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.2/tailwindcss-linux-x64
chmod +x bin/tailwindcss
./bin/tailwindcss -i ./static/css/input.css -o ./static/css/tailwind.css --watch
```

(swap `linux-x64` for your platform's asset name from the [releases page](https://github.com/tailwindlabs/tailwindcss/releases) — e.g. `macos-arm64` on Apple Silicon)

Markdown-rendered post/comment bodies use the bundled `@tailwindcss/typography` plugin (the `prose` class) rather than hand-styling arbitrary HTML — the standalone CLI ships official plugins like this without needing npm.

## Tests

```sh
docker compose run --rm web python manage.py test
```

## Build verification

```sh
./scripts/build-test.sh
```

Builds the image, brings up Postgres, runs migrations, runs the test suite, and runs `manage.py check --deploy`.
