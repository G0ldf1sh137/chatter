# Design Plan — "Chatter" (working title)

A simple social media web app built with Django. Users register, create posts, and comment on posts or on other comments (unlimited nesting). Everything runs in Docker with Postgres, and the Docker build doubles as the project's build test.

## 1. Goals and scope

The first version delivers user registration and login (username/password via Django's built-in auth), user profile pages showing a user's posts and a short bio, text posts on a shared public feed, and threaded comments with unlimited nesting. Posts and comments are authored in Markdown and render as formatted HTML when published (see §5.1). Pages are server-rendered with Django templates — no separate frontend build, no REST API, no JavaScript framework.

Explicitly out of scope for v1: email verification, likes/reactions, following/friends, direct messages, image uploads, search, and moderation tools. The data model below leaves room for these later without schema rewrites.

## 2. Tech stack

Python 3.12, Django 5.x, PostgreSQL 16 (official Docker image), psycopg 3 as the database driver, Gunicorn as the app server inside the container, and Django's template engine with a small amount of vanilla CSS for styling. Markdown rendering uses `markdown-it-py` (CommonMark-compliant) with `nh3` for HTML sanitization. Dependencies are managed with `uv`: declared in `pyproject.toml`, locked in `uv.lock` (committed), so every environment — dev, Docker build, CI — installs the exact same versions with `uv sync`. Configuration (secret key, debug flag, database URL) comes from environment variables so the same image works in dev and in build tests.

## 3. Project layout

```
chatter/
├── manage.py
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── config/                 # Django project (settings, urls, wsgi)
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/               # registration, login, profiles
│   ├── models.py           # Profile
│   ├── views.py
│   ├── urls.py
│   └── templates/accounts/
├── posts/                  # posts and comments
│   ├── models.py           # Post, Comment
│   ├── views.py
│   ├── urls.py
│   └── templates/posts/
└── templates/              # base.html, shared layout
```

Two small apps keep concerns separated: `accounts` owns everything about users, `posts` owns content. Django's built-in `User` model is used directly (no custom user model needed for v1 — Django's docs recommend a custom model for greenfield projects, but the built-in one plus a `Profile` keeps this simple; if we'd rather future-proof, swapping to a minimal custom user model is a one-line decision that must be made before the first migration, so it's flagged here as the one irreversible choice).

## 4. Data model

**User** — Django's built-in `auth.User` (username, password hash, email, joined date).

**Profile** — one-to-one with User. Fields: `bio` (text, optional), `created_at`. Created automatically via a `post_save` signal when a user registers. Avatar images are deferred to a later version to avoid file-upload handling in v1.

**Post** — `author` (FK → User, `on_delete=CASCADE`), `body` (text, max ~5,000 chars), `created_at`, `updated_at`. Ordered newest-first on the feed. Index on `created_at`.

**Comment** — `author` (FK → User), `post` (FK → Post, always set, even for nested replies — this makes "all comments for this post" one query), `parent` (FK → self, nullable; null means a top-level comment on the post), `body` (text), `created_at`. Indexes on `(post, created_at)` and `parent`.

Threading strategy: fetch all comments for a post in one query, then build the tree in Python (a dict of `parent_id → children`). This is O(n), avoids recursive SQL, and is plenty fast for the comment volumes a simple app will see. If threads ever get huge, this can later be swapped for a recursive CTE or django-mptt without changing the schema.

Deletion policy: deleting a user cascades to their posts and comments in v1 (simplest correct behavior). A "deleted comment placeholder" approach (keep the row, blank the body) can come later if orphaned threads become a problem.

## 5. URLs and views

| URL | View | Purpose |
|---|---|---|
| `/` | feed | All posts, newest first, paginated |
| `/register/` | register | Signup form (Django `UserCreationForm`) |
| `/login/`, `/logout/` | auth | Django's built-in auth views |
| `/users/<username>/` | profile | Bio + that user's posts |
| `/posts/new/` | create post | Login required |
| `/posts/<id>/` | post detail | Post + full comment tree + comment form |
| `/posts/<id>/comment/` | add comment | POST only; optional `parent` field for replies |

Views are Django class-based where they map cleanly (ListView for the feed, CreateView for posts) and function-based where a form does two jobs (the comment view). All write actions require login and CSRF; users can only edit/delete their own content (enforced in the view, checked in tests).

### 5.1 Markdown rendering

Post and comment bodies are stored as the raw Markdown the user typed — the database never holds rendered HTML for these fields, so the renderer or sanitizer can be upgraded later and every post benefits immediately. Rendering happens at display time through a single `render_markdown` template filter shared by posts and comments.

The pipeline is: `markdown-it-py` converts Markdown to HTML (CommonMark plus useful extras: fenced code blocks, tables, strikethrough, autolinked URLs), then `nh3` (a Rust-backed HTML sanitizer, the maintained successor to bleach) strips everything outside an allowlist of tags and attributes. This second step is what makes user-authored Markdown safe: raw HTML embedded in Markdown, `javascript:` hrefs, `<script>` tags, and event-handler attributes are all removed rather than escaped-and-broken. The sanitized output is marked safe for the template. Links additionally get `rel="nofollow noopener"` via nh3's link cleaning.

Deliberate limits for v1: no image embedding via Markdown (`![]()` is stripped by the allowlist) since we're deferring media handling entirely; no syntax highlighting of code blocks (they render as plain `<pre><code>`, and highlight.js can be layered on later without model changes). Rendering cost is negligible at this scale, so no caching of rendered HTML in v1; if the feed ever gets hot, Django's template fragment caching is the drop-in fix.

The post form gets a plain textarea with a short "Markdown supported" hint; a live preview is a nice-to-have that can ride along with the HTMX-style enhancements later.

The comment form on the post detail page includes a hidden `parent` input. "Reply" links pre-fill it. Replies render indented under their parent via a recursive template include with the pre-built tree passed in context.

## 6. Docker setup

Two services in `docker-compose.yml`:

**db** — `postgres:16` image, credentials from `.env`, a named volume for data persistence, and a healthcheck (`pg_isready`) so the app waits for a ready database rather than crashing on first boot.

**web** — built from the project `Dockerfile`. Base image `python:3.12-slim` with the `uv` binary copied in from the official `ghcr.io/astral-sh/uv` image (a single static binary, no extra layer weight). Dependency install is its own cached layer: copy just `pyproject.toml` + `uv.lock`, run `uv sync --frozen --no-dev` into a project virtualenv, then copy the source — so code changes never re-trigger a dependency install, and `--frozen` guarantees the build fails loudly if the lockfile is out of date rather than silently resolving new versions. The container runs as a non-root user with the venv on `PATH`. The container entrypoint runs `migrate` and then starts the server — Django's dev server (`runserver`) when `DEBUG=1` for auto-reload during development, Gunicorn otherwise. The compose file bind-mounts the source directory in dev so code changes reload without rebuilding.

`.env.example` documents every variable (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`); the real `.env` is gitignored.

Daily workflow: `docker compose up` brings up the whole stack at `http://localhost:8000`. `docker compose run --rm web python manage.py <cmd>` for one-off management commands. Adding a dependency is `uv add <package>` (updates `pyproject.toml` and `uv.lock` together) followed by a rebuild; working outside Docker (editor tooling, quick scripts) is `uv sync` locally, which creates `.venv/` from the same lockfile.

## 7. Build and test verification

The build test the request asks for is exactly: `docker compose build` must succeed from a clean checkout, and `docker compose up` must produce a working app. To make that check meaningful and automatable, the plan adds a test target: `docker compose run --rm web python manage.py test` runs the Django test suite against a throwaway Postgres test database inside the same network.

Test coverage in v1: registration flow (valid signup, duplicate username), auth-gating (anonymous users can't post/comment), post creation and feed ordering, comment creation including nested replies, correct tree construction for a multi-level thread, and permission checks (can't edit someone else's post). Markdown rendering gets its own test group: headings/bold/lists/code blocks render to the expected HTML, and — most importantly — XSS attempts (`<script>` tags, `javascript:` links, `onerror` attributes, raw HTML passthrough) are verified to be stripped from the rendered output. Also a `python manage.py check --deploy` pass in the non-debug configuration to catch obvious settings problems.

A single script (`./scripts/build-test.sh`) chains build → up db → migrate → test, so "does the project build" is one command, suitable for CI later.

## 8. Build plan (increments)

1. Skeleton that runs: Django project + Dockerfile + docker-compose with Postgres; a placeholder homepage renders at localhost:8000; `docker compose build` passes.
2. Auth: registration, login, logout; base template with nav that reflects auth state.
3. Posts: create post + public feed with pagination; tests for auth-gating and ordering.
4. Markdown rendering: the `render_markdown` filter (markdown-it-py + nh3), applied to post bodies; rendering and XSS-stripping tests.
5. Comments: flat comments on posts first, then nesting (parent FK, tree building, indented rendering); comments reuse the markdown filter; tests for the tree logic.
6. Profiles: profile model + signal, profile page with bio and the user's posts.
7. Build-test polish: the `build-test.sh` script, `check --deploy` cleanup, README with setup instructions.

Each increment ends with the stack running in Docker and its tests passing.

## 9. Risks and open decisions

The one decision to confirm before writing the first migration: stick with Django's built-in `User` (as planned) or start with a minimal custom user model. Everything else in this plan is reversible. Comment-tree performance is the main scaling caveat, addressed above with a clear upgrade path. Static files are served by Django in dev; if this ever deploys for real, WhiteNoise is the drop-in answer and the Dockerfile already leaves room for a `collectstatic` step.
