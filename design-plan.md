# Design Plan — "Chatter"

A social media web app built with Django. Users register (username/password or Google), post in Markdown, comment with unlimited nesting, upvote/downvote posts and comments, follow each other, and maintain a profile with an avatar, bio, and karma. Everything runs in Docker with Postgres, and the Docker build doubles as the project's build test.

This document originally described a v1 plan and has been updated in place to describe what's actually built. §1–§8 describe the current system; §9 records what changed since the original v1 scope and why.

## 1. Goals and scope

The app delivers: user registration and login (username/password via Django's built-in auth, or "Continue with Google" via `django-allauth`), user profiles (bio, avatar, join date, post/comment/follower/following counts, karma), text posts on a public feed sorted by popularity, threaded comments with unlimited nesting, upvote/downvote on both posts and comments (with an automatic self-upvote on your own content), and a follow system with a "Following" feed alongside the main feed. Posts and comments are authored in Markdown and render as formatted HTML when published (see §5.1). Pages are server-rendered with Django templates — no REST API, no JavaScript framework, and no Node.js anywhere in the stack (styling uses Tailwind CSS via its standalone CLI binary, not npm — see §5.3).

Still out of scope: email verification, direct messages, image embedding inside Markdown post/comment bodies (avatars are the only image upload), full-text search, and moderation tools. The data model leaves room for these later without schema rewrites.

## 2. Tech stack

Python 3.12, Django 5.x, PostgreSQL 16 (official Docker image), psycopg 3 as the database driver, Gunicorn as the app server inside the container, and Django's template engine styled with Tailwind CSS (standalone CLI, no Node/npm — see §5.3). Markdown rendering uses `markdown-it-py` (CommonMark-compliant) with `nh3` for HTML sanitization. `django-allauth` provides Google OAuth alongside the built-in username/password auth. `Pillow` backs the avatar `ImageField`. Dependencies are managed with `uv`: declared in `pyproject.toml`, locked in `uv.lock` (committed), so every environment — dev, Docker build, CI — installs the exact same versions with `uv sync`. Configuration (secret key, debug flag, database URL, Google OAuth credentials) comes from environment variables so the same image works in dev and in build tests.

## 3. Project layout

```
chatter/
├── manage.py
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── .env.example
├── scripts/
│   └── build-test.sh
├── config/                         # Django project (settings, urls, wsgi)
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/                       # registration, login, profiles, follows
│   ├── models.py                   # Profile, Follow
│   ├── signals.py                  # auto-create Profile on user creation
│   ├── forms.py                    # RegistrationForm, ProfileForm
│   ├── views.py
│   ├── urls.py
│   └── templates/accounts/         # login, register, profile, profile_edit
├── posts/                          # posts, comments, voting
│   ├── models.py                   # Post, Comment, PostVote, CommentVote
│   ├── signals.py                  # auto-upvote own posts/comments
│   ├── markdown.py                 # render_markdown (markdown-it-py + nh3)
│   ├── forms.py                    # PostForm, CommentForm
│   ├── views.py                    # feed, following-feed, CRUD, voting
│   ├── urls.py
│   ├── templatetags/post_extras.py # {{ body|markdown }} filter
│   └── templates/posts/            # feed, post_detail, post_form, _comment
├── static/css/
│   ├── input.css                   # Tailwind source (@theme, @layer base)
│   └── tailwind.css                # compiled output, gitignored
└── templates/                      # base.html + shared partials
    ├── base.html
    ├── _avatar.html
    ├── _post_vote.html
    └── _comment_vote.html
```

Two apps keep concerns separated: `accounts` owns everything about users and the relationships between them, `posts` owns content and reactions to it. Django's built-in `User` model is used directly (the one decision flagged as irreversible in the original plan — confirmed before the first migration and never revisited).

## 4. Data model

**User** — Django's built-in `auth.User` (username, password hash, email, joined date). Email is required at registration (`RegistrationForm` extends `UserCreationForm`); Google-created accounts get a real email from Google automatically.

**Profile** — one-to-one with User. Fields: `bio` (text, optional), `avatar` (`ImageField`, optional, capped at `MAX_AVATAR_UPLOAD_SIZE` — 2MB — validated in `ProfileForm.clean_avatar`), `created_at`. Created automatically via a `post_save` signal on User (`accounts/signals.py`) — this covers both registration paths, since Google sign-in also creates a standard `User` row through the same manager.

**Follow** — `follower` (FK → User, `related_name="following"`), `followed` (FK → User, `related_name="followers"`), `created_at`. A `UniqueConstraint` on `(follower, followed)` prevents duplicate follows; a `CheckConstraint` prevents self-follows at the database level, not just in the view.

**Post** — `author` (FK → User, `on_delete=CASCADE`), `body` (text, max ~5,000 chars), `created_at`, `updated_at`. Default ordering is `-created_at`, but the feed itself orders by score (see §5).

**Comment** — `author` (FK → User), `post` (FK → Post, always set, even for nested replies), `parent` (FK → self, nullable; null means top-level), `body` (text), `created_at`.

**PostVote** / **CommentVote** — both subclass an abstract `Vote` base (`user`, `value` — `+1`/`-1` via `Vote.UP`/`Vote.DOWN`, `created_at`) rather than a single generic-relation model, since there are only ever two votable types and duplicating a three-field model twice is simpler than `ContentType`/`GenericForeignKey` machinery. Each has a `UniqueConstraint` on `(user, post)` / `(user, comment)` — one vote per user per item, flipped or removed by voting again rather than accumulating rows.

Threading strategy (unchanged from v1): fetch all comments for a post in one query, build the tree in Python (`build_comment_tree`, a dict of `parent_id → children`). O(n), avoids recursive SQL.

Deletion policy (unchanged): deleting a user cascades to their posts, comments, votes, and follows.

## 5. URLs and views

| URL | View | Purpose |
|---|---|---|
| `/` | `FeedView` | All posts, sorted by score then recency, paginated |
| `/following/` | `FollowingFeedView` | Same, filtered to authors the current user follows; login required |
| `/register/` | `RegisterView` | Signup form (username, email, password) |
| `/login/`, `/logout/` | Django's built-in auth views | |
| `/accounts/google/login/` | django-allauth | Google OAuth entry point, linked from login/register as "Continue with Google" |
| `/users/<username>/` | `ProfileView` | Bio, avatar, counts, karma, recent posts and comments |
| `/settings/profile/` | `ProfileEditView` | Edit bio/avatar; login required, always edits `request.user`'s own profile |
| `/users/<username>/follow/`, `/users/<username>/unfollow/` | `FollowView`, `UnfollowView` | POST only; login required |
| `/posts/new/` | `PostCreateView` | Login required |
| `/posts/<id>/` | `PostDetailView` | Post + full comment tree + comment form |
| `/posts/<id>/edit/` | `PostEditView` | Author only (`UserPassesTestMixin`) |
| `/posts/<id>/comment/` | `CommentCreateView` | POST only; optional `parent` field for replies |
| `/posts/<id>/upvote/`, `/posts/<id>/downvote/` | `PostVoteView` | POST only; login required |
| `/comments/<id>/upvote/`, `/comments/<id>/downvote/` | `CommentVoteView` | POST only; login required |

All write actions require login and CSRF; users can only edit their own content (enforced in the view, checked in tests).

### 5.1 Markdown rendering

Unchanged from v1: post and comment bodies are stored as raw Markdown, never rendered HTML. `markdown-it-py` (CommonMark plus fenced code blocks, tables, strikethrough, and linkify for bare URLs) converts to HTML, then `nh3` strips everything outside an allowlist of tags/attributes — this is what makes user-authored Markdown safe against `<script>` tags, `javascript:` hrefs, and event-handler attributes. Links get `rel="nofollow noopener"`. Rendered via a single `render_markdown` template filter shared by posts and comments. Still no image embedding via Markdown and no code syntax highlighting.

### 5.2 Voting and karma

Clicking a vote arrow toggles it: clicking the same direction again removes the vote, clicking the opposite direction flips it (`toggle_vote` in `posts/views.py`). A `post_save` signal (`posts/signals.py`, guarded on `created=True`) automatically gives every new post and comment a self-upvote from its author — this fires regardless of how the row is created (view, admin, shell), not just through `PostCreateView`/`CommentCreateView`.

Score and "did the current user vote, and which way" are computed via `annotate_votes()`, shared across the feed, post detail, and profile post/comment lists: `Coalesce(Sum("votes__value"), 0)` for score, a correlated `Subquery` against the vote table for the current user's vote direction. One gotcha worth documenting: aggregation via `.annotate()` silently drops a queryset's ordering (explicit or the model's default `Meta.ordering`) from the generated SQL, so `annotate_votes()` re-captures and reapplies whatever ordering was present beforehand. Sorting the feed by score itself requires ordering *after* `annotate_votes()` runs, since `order_by()` validates field/alias names immediately — `order_by("-score")` raises `FieldError` if called before the `score` annotation exists on the queryset.

Karma on the profile page is the sum of vote values across all of a user's posts and comments (two aggregate queries, `PostVote`/`CommentVote` filtered by `post__author`/`comment__author`).

### 5.3 Styling

Tailwind CSS, via the [standalone CLI binary](https://tailwindcss.com/blog/standalone-cli) rather than a Node/npm toolchain — the Dockerfile downloads a pinned, architecture-aware binary the same way it already vendors the `uv` binary, so the stack stays Python-only. Source is `static/css/input.css` (a `@theme` block for the brand colors, a small `@layer base` for global element defaults — link color, button/input base styles, and an explicit `color-scheme: light` / white background, which the previous hand-rolled stylesheet declared unconditionally and is easy to forget when moving off it, since without it the app renders in dark mode under a dark system preference); compiled output is `static/css/tailwind.css` (gitignored, generated). Markdown-rendered post/comment bodies use the bundled `@tailwindcss/typography` plugin (the `prose` class) instead of hand-styling arbitrary HTML — the standalone CLI ships the official first-party plugins without needing npm. The reply-toggle "checkbox hack" (see below) uses Tailwind's `peer`/`peer-checked` variants.

The comment form is inline per-comment rather than a single shared form at the bottom of the page: each comment has its own collapsible reply form, expanded via a hidden checkbox and a `<label>`, with no JavaScript — matching the "no JS framework" goal while avoiding the earlier design's jump-to-bottom-of-page UX.

## 6. Docker setup

Two services in `docker-compose.yml`, unchanged in shape from v1:

**db** — `postgres:16`, credentials from `.env`, a named volume, a healthcheck so the app waits for a ready database.

**web** — built from the project `Dockerfile`. Base image `python:3.12-slim` with `curl`/`ca-certificates` installed (needed to fetch the Tailwind CLI binary — see §5.3), the `uv` binary copied from `ghcr.io/astral-sh/uv`, and the Tailwind CLI binary downloaded for the build's `$TARGETARCH` (`amd64`/`arm64`). Dependency install is its own cached layer (`uv sync --frozen --no-dev`) so code changes don't re-trigger it; the Tailwind CSS build runs after the source is copied in (`RUN tailwindcss -i ... -o ... --minify`). The container runs as a non-root user. `docker-entrypoint.sh` runs `migrate`, then either `runserver` with a background `tailwindcss --watch` process (when `DEBUG=1`, so editing a template's classes recompiles the CSS live) or a one-shot minified Tailwind build followed by Gunicorn. The compose file bind-mounts the source directory in dev.

`.env.example` documents every variable, including `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` (see the README for how to obtain them); the real `.env` is gitignored, as is `media/` (uploaded avatars) and the compiled `tailwind.css`.

Daily workflow is unchanged: `docker compose up`, `docker compose run --rm web python manage.py <cmd>` for one-offs, `uv add <package>` + rebuild for new dependencies. Working outside Docker (`uv sync` + `manage.py runserver`) falls back to SQLite when `POSTGRES_DB` isn't set — but the Tailwind CLI has to be run separately in that case (fetched once, run in `--watch` mode alongside `runserver`; see the README).

## 7. Build and test verification

Unchanged in mechanism: `docker compose build` must succeed from a clean checkout, `docker compose up` must produce a working app, and `docker compose run --rm web python manage.py test` runs the suite against a throwaway Postgres database. `./scripts/build-test.sh` chains build → up db → migrate → test → `check --deploy` into one command.

Test coverage has grown alongside the feature set (47 tests as of this writing) — registration (including the required-email field), Google-account auto-profile-creation, auth-gating, post/comment CRUD and permissions, comment tree construction, Markdown rendering and XSS-stripping, follow/unfollow (including the self-follow and duplicate-follow constraints), voting (toggle/flip/remove, anonymous rejection, score aggregation), the automatic self-upvote signal, karma computation, and feed ordering (both the tied-score/newest-first tiebreak and the score-first primary sort).

## 8. Current status

All of §1's goals are implemented and covered by tests. The build plan below is historical — kept for context on how the app was built incrementally — but every increment listed, plus everything in §9, is done.

<details>
<summary>Original v1 build plan (completed)</summary>

1. Skeleton that runs: Django project + Dockerfile + docker-compose with Postgres; a placeholder homepage renders at localhost:8000; `docker compose build` passes.
2. Auth: registration, login, logout; base template with nav that reflects auth state.
3. Posts: create post + public feed with pagination; tests for auth-gating and ordering.
4. Markdown rendering: the `render_markdown` filter (markdown-it-py + nh3), applied to post bodies; rendering and XSS-stripping tests.
5. Comments: flat comments on posts first, then nesting (parent FK, tree building, indented rendering); comments reuse the markdown filter; tests for the tree logic.
6. Profiles: profile model + signal, profile page with bio and the user's posts.
7. Build-test polish: the `build-test.sh` script, `check --deploy` cleanup, README with setup instructions.

</details>

## 9. What changed since v1, and why

Each of these was scope explicitly excluded by §1 of the original plan, added afterward on request rather than pre-planned:

- **Google sign-in** (`django-allauth`) — offered alongside username/password, not a replacement. Configured via `SOCIALACCOUNT_PROVIDERS` in settings rather than allauth's DB-backed `SocialApp`, so credentials are plain environment variables like everything else in this project.
- **Follow/unfollow** — a `Follow` model plus a "Following" feed tab. Was explicitly out of scope in the original v1 ("following/friends"); added because the profile pages made "who's connected to whom" a natural next question.
- **Expanded profiles** — avatar upload (explicitly deferred in the original Profile model design to avoid file-upload handling in v1), join date, comment history alongside posts, and accurate counts. Avatars are the one place this app now does handle file uploads; see the README for the storage caveat (local disk, fine for one container, not for scaling past one).
- **Required email + karma + voting** — none of these were anticipated in the original data model, but none of them required a schema *rewrite* either, which was the explicit design goal of the original plan ("the data model below leaves room for these later without schema rewrites") — `PostVote`/`CommentVote` and `Follow` are additive tables, not migrations of existing ones.
- **Tailwind CSS** — the original plan called for "a small amount of vanilla CSS," which was true through the "Show author avatars" milestone but stopped scaling once vote widgets, follow buttons, and profile stat lines piled up. Kept the "no Node.js" spirit of the original plan by using Tailwind's standalone CLI instead of the conventional npm-based setup.

## 10. Risks and open decisions

Comment-tree performance is still the main scaling caveat, addressed in §4 with a clear upgrade path (recursive CTE or django-mptt) if it's ever needed. Avatar storage on local disk is the other one — noted in the README, S3-compatible storage via `django-storages` is the drop-in fix if this deploys somewhere that isn't a single container. Static files are served by Django in dev; WhiteNoise remains the drop-in answer if this ever deploys for real.
