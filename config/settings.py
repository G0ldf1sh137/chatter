"""
Django settings for the Chatter project.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-only-change-me")

DEBUG = env_bool("DEBUG", False)

# Render sets RENDER=true automatically on every service it runs - used below
# to scope proxy-trusting/SSL-redirect settings to "definitely behind
# Render's TLS-terminating edge," rather than to "DEBUG=False for any
# reason," since forcing an HTTPS redirect with no HTTPS listener in front
# (e.g. DEBUG=0 used locally, or on some other host with no such proxy)
# would make the app completely inaccessible.
IS_RENDER = env_bool("RENDER", False)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
    "posts",
    "games",
    "simulations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

if not DEBUG:
    # WhiteNoise serves collectstatic's output directly from the app process
    # - no separate static file host, which matters on a PaaS like Render
    # that just runs the Dockerfile's gunicorn process with nothing in front
    # of it. Skipped in dev/test, which never run collectstatic and already
    # get static files from django.contrib.staticfiles + runserver.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "games.context_processors.your_turn_count",
                "posts.context_processors.unread_messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# DATABASE_URL (the Render/Neon convention - a single connection string) takes
# priority; falls back to the discrete POSTGRES_* vars Docker Compose supplies
# locally, then to SQLite so local tooling works without Postgres at all.
if os.environ.get("DATABASE_URL"):
    DATABASES = {
        # conn_max_age=0 (no persistent connections) is deliberate: Neon's
        # commonly-copied connection string routes through PgBouncer in
        # transaction-pooling mode, and Django holding a connection open
        # across requests on top of that can surface as "prepared statement
        # already exists" errors or session state (SET, advisory locks)
        # leaking across unrelated requests.
        "default": dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=0, ssl_require=True)
    }
elif os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# The manifest storage requires a collectstatic run (done at Docker image
# build time - see Dockerfile), so dev/test - which never run collectstatic -
# keep the plain storage instead of erroring on every {% static %} lookup.
STATICFILES_STORAGE_BACKEND = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# Local disk by default (fine for dev, and technically works in production -
# but Render's free tier has ephemeral disk, so uploaded avatars are silently
# wiped on every redeploy/restart). Set AWS_STORAGE_BUCKET_NAME to switch to
# S3-compatible storage instead (works with AWS S3 or any S3-compatible host
# such as Cloudflare R2 or Backblaze B2 via AWS_S3_ENDPOINT_URL) - the
# drop-in fix design-plan.md already calls for.
DEFAULT_STORAGE_BACKEND = "django.core.files.storage.FileSystemStorage"
if os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    DEFAULT_STORAGE_BACKEND = "storages.backends.s3.S3Storage"
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "auto")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL")  # only needed for non-AWS S3-compatible hosts
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False

STORAGES = {
    "default": {"BACKEND": DEFAULT_STORAGE_BACKEND},
    "staticfiles": {"BACKEND": STATICFILES_STORAGE_BACKEND},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Max upload size for user-submitted images (avatars), enforced in accounts.forms.
MAX_AVATAR_UPLOAD_SIZE = 2 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "feed"
LOGOUT_REDIRECT_URL = "feed"

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

if IS_RENDER:
    # Render terminates TLS at its edge and forwards plain HTTP to the app
    # with this header set, so Django needs to be told to trust it -
    # otherwise SECURE_SSL_REDIRECT sees every request as already-HTTP and
    # loops redirecting forever. Gated on IS_RENDER specifically (not just
    # DEBUG=False) since forcing an HTTPS redirect anywhere without a proxy
    # like this in front would make the app completely inaccessible.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # Conservative starting value (1 week, not the commonly-recommended 1
    # year) since HSTS is cached by the browser and hard to undo if something
    # about the deploy turns out to be wrong - raise it once confirmed working.
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True


# Email
# Console backend in dev prints verification emails to the runserver log
# instead of requiring real SMTP. Set EMAIL_HOST for a real backend (prod).
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@chatter.local")

# How long an email verification link stays valid.
EMAIL_VERIFICATION_MAX_AGE = 3 * 24 * 60 * 60  # 3 days, in seconds


# django-allauth
# Google is the only social provider for v1; username/password (accounts app)
# remains the primary flow, so allauth's own account templates are unused.
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            "secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
    }
}
