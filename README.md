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

## Tests

```sh
docker compose run --rm web python manage.py test
```

## Build verification

```sh
./scripts/build-test.sh
```

Builds the image, brings up Postgres, runs migrations, runs the test suite, and runs `manage.py check --deploy`.
