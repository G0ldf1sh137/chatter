FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ARG TAILWIND_VERSION=v4.3.2
ARG TARGETARCH
RUN TW_ARCH=$(case "$TARGETARCH" in amd64) echo x64 ;; arm64) echo arm64 ;; *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; esac) \
    && curl -fsSL -o /usr/local/bin/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-${TW_ARCH}" \
    && chmod +x /usr/local/bin/tailwindcss

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN groupadd -r app && useradd -r -g app app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN tailwindcss -i ./static/css/input.css -o ./static/css/tailwind.css --minify

# Baked into the image at build time, not run on every container start -
# deterministic given the code above it, so redoing it on every boot/restart
# would just be repeated work sitting in front of gunicorn for no benefit.
# .dockerignore excludes .env, so DEBUG naturally defaults to False here,
# matching production and selecting WhiteNoise's manifest storage backend.
# input.css (the Tailwind *source*, not the compiled output) is excluded -
# its `@import "tailwindcss"` line isn't a real file reference, and
# WhiteNoise's manifest post-processor errors trying to resolve it as one.
RUN python manage.py collectstatic --noinput --ignore=input.css

RUN chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
