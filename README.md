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

Avatars are stored on local disk under `media/` (gitignored) and served directly by Django in dev. That's fine for a single-container demo but won't survive a redeploy or scale past one instance — set `AWS_STORAGE_BUCKET_NAME` (and friends, see `.env.example`) to switch to S3-compatible storage instead; see [Deploying](#deploying) below. Max upload size is capped at 2MB (`MAX_AVATAR_UPLOAD_SIZE` in settings).

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

## Deploying

Free-tier deployment target: **Render** (runs the existing `Dockerfile` directly, no code changes needed beyond what's already in this repo) + **Neon** (serverless Postgres). Both have generous, non-time-limited free tiers.

### 1. Create the database (Neon)

1. Sign up at [neon.tech](https://neon.tech) and create a project.
2. On the project dashboard, copy the **connection string** (Neon shows it as a full `postgres://...` URL, already including `?sslmode=require`). You'll paste this into Render as `DATABASE_URL` in step 3.
3. Either connection string variant Neon offers (pooled, with `-pooler` in the hostname, or direct) works here — `conn_max_age=0` in `config/settings.py` deliberately avoids holding a persistent connection open, so it won't fight Neon's PgBouncer pooling either way.

### 2. Deploy the app (Render)

1. Sign up at [render.com](https://render.com) and connect your GitHub account.
2. **New > Blueprint**, and point it at this repo. Render reads `render.yaml` at the repo root and provisions a single Docker-based web service on the free plan.
3. Render will prompt for the blueprint's `sync: false` env vars before the first deploy, or you can fill them in afterward under the service's **Environment** tab:
   - `DATABASE_URL` — the Neon connection string from step 1.
   - `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` — optional, see below.
   - `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `DEFAULT_FROM_EMAIL` — optional, see below.
   - `ALLOWED_HOSTS` — leave blank for now; Render doesn't know the service's hostname until after the first deploy (see step 4).
   - `SECRET_KEY` is generated for you automatically (`generateValue: true` in `render.yaml`) — you don't need to set it.
4. Deploy. Once it's live, Render shows the assigned hostname (`<service-name>.onrender.com`, or check the service's **Settings** tab). Go back to **Environment** and set:
   ```
   ALLOWED_HOSTS=<service-name>.onrender.com
   ```
   then let it redeploy. Until this is set, Django rejects every request with a 400 (`DisallowedHost`) — including Render's own health check, so the service may show as unhealthy until this step is done.
5. Visit the site. First registration/login should work immediately with username/password (email verification links print to Render's log viewer if `EMAIL_HOST` isn't set — see below).

### 3. Optional: real outgoing email

Without `EMAIL_HOST` set, verification emails aren't sent — they print to Render's log viewer instead (**Logs** tab), same as the local dev console backend. That's fine for trying things out, but you'll want real email for actual users. Any SMTP provider works; a few with usable free tiers: Brevo (300 emails/day free), Resend, or Mailgun's trial tier. Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` in Render's environment settings once you have credentials from one.

### 4. Optional: Google sign-in

If you want "Continue with Google" to work on the deployed site, add a second **Authorized redirect URI** in the same Google Cloud Console OAuth client from the [Google sign-in](#google-sign-in) section above:
```
https://<service-name>.onrender.com/accounts/google/login/callback/
```
then set `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` in Render's environment (same values as local dev — one OAuth client can have multiple redirect URIs registered).

### 5. Optional: persistent avatar storage

Render's free-tier web service has **ephemeral disk** — uploaded avatars are wiped on every redeploy/restart unless you switch to S3-compatible storage. [Cloudflare R2](https://developers.cloudflare.com/r2/) has a permanent free tier (10GB storage, no egress fees) and works as a drop-in S3-compatible backend. Once you have a bucket and API token, set in Render's environment:
```
AWS_STORAGE_BUCKET_NAME=<your-bucket-name>
AWS_ACCESS_KEY_ID=<r2-access-key-id>
AWS_SECRET_ACCESS_KEY=<r2-secret-access-key>
AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
```
Leave these unset to keep local disk storage (fine until you care about avatars surviving a redeploy).

### Known free-tier limitations

- Render's free web service **spins down after ~15 minutes of inactivity**; the next request pays a cold-start delay (usually a few seconds) while it wakes back up.
- Neon's free tier also autosuspends its compute after a period of inactivity, with a similar (usually sub-second to a few seconds) wake-up delay on the next query.
- Neither of these affects correctness — just expect the first request after a quiet period to be slower than the rest.
