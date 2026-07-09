# Design Plan — "Chatter"

A social media web app built with Django. Users register (username/password or Google) after verifying their email, post in Markdown, comment with unlimited nesting, upvote/downvote posts and comments, follow each other, maintain a profile with an avatar, bio, and karma, and play simple games — both single-player and turn-based multiplayer — against each other. Everything runs in Docker with Postgres, and the Docker build doubles as the project's build test.

This document originally described a v1 plan and has been updated in place to describe what's actually built. §1–§8 describe the current system; §9 records what changed since the original v1 scope and why.

## 1. Goals and scope

The app delivers: user registration and login (username/password via Django's built-in auth, or "Continue with Google" via `django-allauth`), email verification gating username/password login, user profiles (bio, avatar, join date, post/comment/follower/following counts, karma, game records) with a manual light/dark theme toggle, text posts on a public feed sorted by popularity, threaded comments with unlimited nesting, upvote/downvote on both posts and comments (with an automatic self-upvote on your own content and an animated re-sort when scores change), a follow system with a "Following" feed alongside the main feed, and a `games` app (Tic-Tac-Toe, Rock-Paper-Scissors, Word Guess, and 2048 — see §5.4). Posts and comments are authored in Markdown and render as formatted HTML when published (see §5.1). Pages are server-rendered with Django templates — no REST API, no JavaScript framework, and no Node.js anywhere in the stack (styling uses Tailwind CSS via its standalone CLI binary, not npm — see §5.3); the one deliberate exception is 2048, where a real client-side game loop is unavoidable (see §5.4).

Still out of scope: direct messages, image embedding inside Markdown post/comment bodies (avatars are the only image upload), full-text search, moderation tools, and real-time multiplayer (games are turn-based/asynchronous by design — see §5.4). The data model leaves room for these later without schema rewrites.

## 2. Tech stack

Python 3.12, Django 5.x, PostgreSQL 16 (official Docker image), psycopg 3 as the database driver, Gunicorn as the app server inside the container, and Django's template engine styled with Tailwind CSS (standalone CLI, no Node/npm — see §5.3). Markdown rendering uses `markdown-it-py` (CommonMark-compliant) with `nh3` for HTML sanitization. `django-allauth` provides Google OAuth alongside the built-in username/password auth. Email verification is hand-rolled (a signed, time-limited token via `django.core.signing`, not allauth's own email-confirmation flow — see §5.1a) since it only needs to gate the site's own registration form, not allauth's. `Pillow` backs the avatar `ImageField`. Dependencies are managed with `uv`: declared in `pyproject.toml`, locked in `uv.lock` (committed), so every environment — dev, Docker build, CI — installs the exact same versions with `uv sync`. Configuration (secret key, debug flag, database URL, Google OAuth credentials, SMTP settings) comes from environment variables so the same image works in dev and in build tests.

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
├── accounts/                       # registration, login, profiles, follows, email verification
│   ├── models.py                   # Profile, Follow
│   ├── signals.py                  # auto-create Profile; auto-verify social signups
│   ├── adapter.py                  # SocialAccountAdapter: link Google login to existing email
│   ├── tokens.py                   # signed email-verification tokens
│   ├── emails.py                   # send_verification_email
│   ├── forms.py                    # RegistrationForm, ProfileForm, EmailVerifiedAuthenticationForm
│   ├── views.py
│   ├── urls.py
│   └── templates/accounts/         # login, register, profile, profile_edit, verification_*
├── posts/                          # posts, comments, voting
│   ├── models.py                   # Post, Comment, PostVote, CommentVote
│   ├── signals.py                  # auto-upvote own posts/comments
│   ├── markdown.py                 # render_markdown (markdown-it-py + nh3)
│   ├── forms.py                    # PostForm, CommentForm
│   ├── views.py                    # feed, following-feed, CRUD, voting, annotate_votes/toggle_vote
│   ├── urls.py
│   ├── templatetags/post_extras.py # {{ body|markdown }} filter
│   └── templates/posts/            # feed, post_detail, post_form, _comment
├── games/                          # single-player and turn-based multiplayer games
│   ├── models.py                   # Match (Tic-Tac-Toe/RPS/Connect Four/Checkers), SinglePlayerResult
│   ├── logic/                      # pure game-rule modules, no Django imports
│   │   ├── tic_tac_toe.py
│   │   ├── rock_paper_scissors.py
│   │   ├── connect_four.py
│   │   ├── checkers.py
│   │   └── hangman.py
│   ├── stats.py                    # win/loss records and leaderboard queries
│   ├── views.py
│   ├── urls.py
│   ├── static/games/js/            # 2048.js, snake.js, doodle_jump.js, checkers.js (move-selection helper)
│   └── templates/games/            # hub, leaderboard, per-game play pages
├── static/css/
│   ├── input.css                   # Tailwind source (@theme, @layer base, view-transition opt-in)
│   └── tailwind.css                # compiled output, gitignored
└── templates/                      # base.html + shared partials
    ├── base.html                   # dark-mode bootstrap script (see §5.3)
    ├── _header.html                # nav + theme toggle
    ├── _avatar.html
    ├── _post_vote.html
    └── _comment_vote.html
```

Three apps keep concerns separated: `accounts` owns everything about users and the relationships between them, `posts` owns content and reactions to it, `games` owns the games and their scores. Django's built-in `User` model is used directly (the one decision flagged as irreversible in the original plan — confirmed before the first migration and never revisited).

## 4. Data model

**User** — Django's built-in `auth.User` (username, password hash, email, joined date). Email is required at registration (`RegistrationForm` extends `UserCreationForm`); Google-created accounts get a real email from Google automatically.

**Profile** — one-to-one with User. Fields: `bio` (text, optional), `avatar` (`ImageField`, optional, capped at `MAX_AVATAR_UPLOAD_SIZE` — 2MB — validated in `ProfileForm.clean_avatar`), `email_verified` (bool, default `False`), `created_at`. Created automatically via a `post_save` signal on User (`accounts/signals.py`) — this covers both registration paths, since Google sign-in also creates a standard `User` row through the same manager. Accounts that existed before `email_verified` was added were grandfathered in as verified by a one-off data migration, so the gate only applies to registrations from that point on.

**Follow** — `follower` (FK → User, `related_name="following"`), `followed` (FK → User, `related_name="followers"`), `created_at`. A `UniqueConstraint` on `(follower, followed)` prevents duplicate follows; a `CheckConstraint` prevents self-follows at the database level, not just in the view.

**Post** — `author` (FK → User, `on_delete=CASCADE`), `body` (text, max ~5,000 chars), `created_at`, `updated_at`. Default ordering is `-created_at`, but the feed itself orders by score (see §5).

**Comment** — `author` (FK → User), `post` (FK → Post, always set, even for nested replies), `parent` (FK → self, nullable; null means top-level), `body` (text), `created_at`.

**PostVote** / **CommentVote** — both subclass an abstract `Vote` base (`user`, `value` — `+1`/`-1` via `Vote.UP`/`Vote.DOWN`, `created_at`) rather than a single generic-relation model, since there are only ever two votable types and duplicating a three-field model twice is simpler than `ContentType`/`GenericForeignKey` machinery. Each has a `UniqueConstraint` on `(user, post)` / `(user, comment)` — one vote per user per item, flipped or removed by voting again rather than accumulating rows.

Threading strategy (unchanged from v1): fetch all comments for a post in one query, build the tree in Python (`build_comment_tree`, a dict of `parent_id → children`). O(n), avoids recursive SQL.

**Match** — one generic model for all four multiplayer games rather than a table per game, since Tic-Tac-Toe, Rock-Paper-Scissors, Connect Four, and Checkers all share an identical shape (2 players, one state blob, one winner) — unlike Post/Comment, which are genuinely different parent objects and justify `Vote`'s abstract-base-plus-subclass split above. Fields: `game` (`"ttt"`/`"rps"`/`"connect4"`/`"checkers"`), `player1`/`player2` (FK → User), `state` (`JSONField`, game-specific shape — a 9-cell board array for Tic-Tac-Toe, a `{"choices": {...}}` map keyed by user ID for Rock-Paper-Scissors' simultaneous picks, a 6×7 nested array for Connect Four, an 8×8 nested array of `"r"`/`"b"`/`"R"`/`"B"` piece codes for Checkers), `status` (`"active"`/`"finished"`), `turn` (FK → User, nullable — null for Rock-Paper-Scissors, which has no "whose turn" concept), `winner` (FK → User, nullable; null on a finished match means a draw), timestamps. A `CheckConstraint` prevents challenging yourself. No constraint blocks multiple concurrent matches between the same two players (an immediate rematch is fine).

**SinglePlayerResult** — one row per completed single-player game. Fields: `player` (FK → User), `game` (`"hangman"`/`"2048"`/`"snake"`/`"doodle"`), `won` (bool), `score` (int), `created_at`. In-progress single-player state doesn't get a DB row: Hangman uses `request.session` (there's already a precedent for session-scratch-state in `accounts/views.py`'s `pending_verification_email`), and 2048/Snake/Doodle Jump are entirely client-side; a `SinglePlayerResult` is only written once a game actually ends. Snake and Doodle Jump have no natural win condition (both are endless score-chasers), so their `Finish` views always record `won=False` — score is the only meaningful signal, same as 2048's leaderboard ranking by high score rather than win count.

Deletion policy (unchanged): deleting a user cascades to their posts, comments, votes, and follows.

## 5. URLs and views

| URL | View | Purpose |
|---|---|---|
| `/` | `FeedView` | All posts, sorted by score then recency, paginated |
| `/following/` | `FollowingFeedView` | Same, filtered to authors the current user follows; login required |
| `/register/` | `RegisterView` | Signup form (username, email, password); sends a verification email instead of logging in |
| `/verification-sent/`, `/verify-email/<token>/`, `/resend-verification/` | `VerificationSentView`, `VerifyEmailView`, `ResendVerificationView` | Email verification flow — see §5.1a |
| `/login/`, `/logout/` | Django's built-in auth views, with a custom `AuthenticationForm` gating unverified accounts | |
| `/accounts/google/login/` | django-allauth | Google OAuth entry point, linked from login/register as "Continue with Google"; auto-links to an existing account with a matching email (`SocialAccountAdapter.pre_social_login`) instead of allauth's default conflict form |
| `/users/<username>/` | `ProfileView` | Bio, avatar, counts, karma, game records, recent posts and comments |
| `/settings/profile/` | `ProfileEditView` | Edit bio/avatar; login required, always edits `request.user`'s own profile |
| `/users/<username>/follow/`, `/users/<username>/unfollow/` | `FollowView`, `UnfollowView` | POST only; login required |
| `/posts/new/` | `PostCreateView` | Login required |
| `/posts/<id>/` | `PostDetailView` | Post + full comment tree + comment form |
| `/posts/<id>/edit/` | `PostEditView` | Author only (`UserPassesTestMixin`) |
| `/posts/<id>/comment/` | `CommentCreateView` | POST only; optional `parent` field for replies |
| `/posts/<id>/upvote/`, `/posts/<id>/downvote/` | `PostVoteView` | POST only; login required |
| `/comments/<id>/upvote/`, `/comments/<id>/downvote/` | `CommentVoteView` | POST only; login required |
| `/games/`, `/games/leaderboard/` | `GamesHubView`, `LeaderboardView` | Hub (your-turn/waiting matches, login required) and public leaderboard — see §5.4 |
| `/games/ttt/...`, `/games/rps/...`, `/games/hangman/...`, `/games/2048/...` | per-game challenge/play/move views | See §5.4 |

All write actions require login and CSRF; users can only edit their own content (enforced in the view, checked in tests).

### 5.1 Markdown rendering

Unchanged from v1: post and comment bodies are stored as raw Markdown, never rendered HTML. `markdown-it-py` (CommonMark plus fenced code blocks, tables, strikethrough, and linkify for bare URLs) converts to HTML, then `nh3` strips everything outside an allowlist of tags/attributes — this is what makes user-authored Markdown safe against `<script>` tags, `javascript:` hrefs, and event-handler attributes. Links get `rel="nofollow noopener"`. Rendered via a single `render_markdown` template filter shared by posts and comments. Still no image embedding via Markdown and no code syntax highlighting.

### 5.1a Email verification

Registering with username/password no longer logs the user in immediately: `RegisterView` emails a signed, expiring link (`django.core.signing`, 3-day max age via `EMAIL_VERIFICATION_MAX_AGE`) and redirects to a "check your email" page. Logging in is blocked until the link is visited — enforced in `EmailVerifiedAuthenticationForm.confirm_login_allowed` (`accounts/forms.py`), the officially-supported Django hook for exactly this kind of gate, rather than fighting with allauth's backend internals. `EMAIL_BACKEND` defaults to Django's console backend in dev (no `EMAIL_HOST` set), so links show up in the server log without needing real SMTP.

Google sign-in is exempt, since Google already verified the email: `accounts/signals.py` hooks allauth's `user_signed_up` signal (which only fires with a `sociallogin` kwarg for social accounts, never for the plain `RegisterView`) to mark those profiles verified immediately. Separately, `accounts/adapter.py`'s `SocialAccountAdapter.pre_social_login` looks up an existing user by the Google-provided email *before* allauth decides whether to show its own signup form, and connects the login to that existing account if one matches — treating a Google-verified email as proof of ownership rather than showing allauth's default (unstyled) conflict-resolution form.

### 5.2 Voting and karma

Clicking a vote arrow toggles it: clicking the same direction again removes the vote, clicking the opposite direction flips it (`toggle_vote` in `posts/views.py`). A `post_save` signal (`posts/signals.py`, guarded on `created=True`) automatically gives every new post and comment a self-upvote from its author — this fires regardless of how the row is created (view, admin, shell), not just through `PostCreateView`/`CommentCreateView`.

Score and "did the current user vote, and which way" are computed via `annotate_votes()`, shared across the feed, post detail, and profile post/comment lists: `Coalesce(Sum("votes__value"), 0)` for score, a correlated `Subquery` against the vote table for the current user's vote direction. One gotcha worth documenting: aggregation via `.annotate()` silently drops a queryset's ordering (explicit or the model's default `Meta.ordering`) from the generated SQL, so `annotate_votes()` re-captures and reapplies whatever ordering was present beforehand. Sorting the feed by score itself requires ordering *after* `annotate_votes()` runs, since `order_by()` validates field/alias names immediately — `order_by("-score")` raises `FieldError` if called before the `score` annotation exists on the queryset.

Karma on the profile page is the sum of vote values across all of a user's posts and comments (two aggregate queries, `PostVote`/`CommentVote` filtered by `post__author`/`comment__author`).

### 5.3 Styling

Tailwind CSS, via the [standalone CLI binary](https://tailwindcss.com/blog/standalone-cli) rather than a Node/npm toolchain — the Dockerfile downloads a pinned, architecture-aware binary the same way it already vendors the `uv` binary, so the stack stays Python-only. Source is `static/css/input.css`; compiled output is `static/css/tailwind.css` (gitignored, generated). Markdown-rendered post/comment bodies use the bundled `@tailwindcss/typography` plugin (the `prose` class) instead of hand-styling arbitrary HTML — the standalone CLI ships the official first-party plugins without needing npm. The reply-toggle "checkbox hack" uses Tailwind's `peer`/`peer-checked` variants.

The color system ("Cobalt Current" — cobalt blue brand, amber upvotes, rose downvotes, emerald karma) is a set of semantic tokens (`--bg`, `--surface`, `--fg`, `--accent`, ...) defined once on `:root` and remapped under `.dark`, then exposed to Tailwind via `@theme { --color-bg: var(--bg); ... }` — templates use `bg-surface`, `text-accent`, etc. throughout rather than raw Tailwind colors or `dark:` variants, so a full palette swap (as happened once already, from an earlier violet/indigo palette) only touches the two variable blocks in `input.css`, never the ~20 templates that reference them. Dark mode is class-based (`@custom-variant dark (&:where(.dark, .dark *));`) rather than Tailwind's `prefers-color-scheme` default, since the header's sun/moon toggle button needs to override the OS preference and persist the choice — a blocking inline script in `base.html`'s `<head>` (before the stylesheet paints) applies `.dark` from `localStorage`, falling back to `prefers-color-scheme` only on a first visit, which avoids a flash of the wrong theme that a deferred/post-paint script wouldn't.

The comment form is inline per-comment rather than a single shared form at the bottom of the page: each comment has its own collapsible reply form, expanded via a hidden checkbox and a `<label>`, with no JavaScript — matching the "no JS framework" goal while avoiding the earlier design's jump-to-bottom-of-page UX.

Voting redirects back to a full page reload with posts re-sorted by score, which would otherwise just snap to the new order. `input.css` opts every navigation into the browser's native cross-document View Transitions API (`@view-transition { navigation: auto; }` — Chrome/Edge 126+, a harmless no-op elsewhere), and `feed.html` gives each post card a stable `view-transition-name` (`post-<id>`), so the browser matches a card across the old and new page and animates it sliding to its new rank instead of jumping. No custom JS.

### 5.4 Games

The `games` app adds Tic-Tac-Toe, Rock-Paper-Scissors, Connect Four, and Checkers (turn-based multiplayer, challenged from a profile page like the Follow relationship — no open lobby, no accept/decline handshake), Word Guess/Hangman (single-player, session-based), and 2048, Snake, and a Doodle Jump clone (single-player, client-side).

Multiplayer is explicitly **turn-based/asynchronous, not real-time** — a deliberate choice to avoid adding Channels/an ASGI server/a Redis channel layer for a feature that doesn't need them. A move is a normal POST + redirect; the opponent sees it next time they load the page. `games/views.py`'s `GamesHubView` groups a player's active matches into "your turn" vs "waiting on opponent" so discovering a pending move doesn't require a notification system. Concurrent move submissions (mainly a concern for Rock-Paper-Scissors, where both players can legitimately move at once) are handled with `select_for_update()` inside `transaction.atomic()`, re-checking `status`/`turn` after acquiring the lock — not a queue or external lock, which would be over-engineering at this scale.

Game rules live in `games/logic/` as pure Python functions with no Django imports (mirroring `posts/markdown.py` as the precedent for keeping rules separate from the view/model layer), directly unit-tested without touching the database. Connect Four's win detection scans all four line directions from every occupied cell. Checkers uses a deliberately simplified ruleset (diagonal moves only, captures optional rather than forced, single jump per turn, kings move any diagonal direction) rather than standard American forced-capture rules — a non-king piece can still capture backward even though it can't simple-move backward, the standard convention, documented explicitly in the module since the simplified spec left it open; there's no draw concept since the lack of forced captures means no mutual-stalemate deadlock, only a one-sided "no legal moves" loss. Checkers' move UX is inherently two clicks (select a piece, then a destination), handled by a small vanilla-JS click helper (`checkers.js`) that fills two hidden form fields and submits — simpler than tracking a "selected piece" in server-side session state, and consistent with the project's "interaction logic in JS, server stays a dumb state-transition validator" split.

2048, Snake, and Doodle Jump are the exceptions to "no client-side game logic": their rules live entirely in `games/static/games/js/`, vanilla JS game loops, since real-time gameplay can't be a server round-trip per move. 2048 implements all four slide directions with a single "slide left" routine plus a rotate-and-rotate-back trick. Snake uses a DOM grid re-rendered each tick (`setTimeout` chaining so the tick rate can speed up as the snake grows). Doodle Jump is the app's first `<canvas>`-based game, using `requestAnimationFrame` for continuous gravity/jump physics with static scrolling platforms (no moving/breakable platforms or enemies — kept to a simple MVP). All three POST just a final score (2048 also sends the highest tile reached) to a `FinishView` at game over; the server does bounds-checking (sane ranges, and for 2048 a power-of-two tile check consistent with the score) rather than full move-replay validation, proportionate to a casual game's stakes.

`games/stats.py` centralizes the win/loss/high-score queries so both `ProfileView` (which cross-imports from `games`, mirroring the existing precedent of importing from `posts` for karma) and the public `/games/leaderboard/` page read from the same source rather than duplicating aggregation logic.

## 6. Docker setup

Two services in `docker-compose.yml`, unchanged in shape from v1:

**db** — `postgres:16`, credentials from `.env`, a named volume, a healthcheck so the app waits for a ready database.

**web** — built from the project `Dockerfile`. Base image `python:3.12-slim` with `curl`/`ca-certificates` installed (needed to fetch the Tailwind CLI binary — see §5.3), the `uv` binary copied from `ghcr.io/astral-sh/uv`, and the Tailwind CLI binary downloaded for the build's `$TARGETARCH` (`amd64`/`arm64`). Dependency install is its own cached layer (`uv sync --frozen --no-dev`) so code changes don't re-trigger it; the Tailwind CSS build runs after the source is copied in (`RUN tailwindcss -i ... -o ... --minify`). The container runs as a non-root user. `docker-entrypoint.sh` runs `migrate`, then either `runserver` with a background `tailwindcss --watch` process (when `DEBUG=1`, so editing a template's classes recompiles the CSS live) or a one-shot minified Tailwind build followed by Gunicorn. The compose file bind-mounts the source directory in dev.

`.env.example` documents every variable, including `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` (see the README for how to obtain them); the real `.env` is gitignored, as is `media/` (uploaded avatars) and the compiled `tailwind.css`.

Daily workflow is unchanged: `docker compose up`, `docker compose run --rm web python manage.py <cmd>` for one-offs, `uv add <package>` + rebuild for new dependencies. Working outside Docker (`uv sync` + `manage.py runserver`) falls back to SQLite when `POSTGRES_DB` isn't set — but the Tailwind CLI has to be run separately in that case (fetched once, run in `--watch` mode alongside `runserver`; see the README).

## 7. Build and test verification

Unchanged in mechanism: `docker compose build` must succeed from a clean checkout, `docker compose up` must produce a working app, and `docker compose run --rm web python manage.py test` runs the suite against a throwaway Postgres database. `./scripts/build-test.sh` chains build → up db → migrate → test → `check --deploy` into one command.

Test coverage has grown alongside the feature set (171 tests as of this writing) — registration (including the required-email field and email verification gate), Google-account auto-profile-creation and email-matched account linking, auth-gating, post/comment CRUD and permissions, comment tree construction, Markdown rendering and XSS-stripping, follow/unfollow (including the self-follow and duplicate-follow constraints), voting (toggle/flip/remove, anonymous rejection, score aggregation), the automatic self-upvote signal, karma computation, feed ordering (both the tied-score/newest-first tiebreak and the score-first primary sort), and the `games` app (pure game-logic unit tests per game, full match flows through the views including turn enforcement and win/draw resolution, session-based Hangman state, 2048 score-submission bounds-checking, and leaderboard/profile-stat accuracy).

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
- **Email verification** (§5.1a) — was explicitly out of scope in the original v1 ("Explicitly out of scope for v1: email verification..."). Hand-rolled rather than adopting allauth's own verification flow wholesale, since allauth's mandatory-verification setting is designed around its own signup/login views and doesn't cleanly gate a separately hand-rolled `RegisterView`/`LoginView` pair.
- **Tailwind CSS, then a full palette redesign, then a manual dark mode toggle** — the original plan called for "a small amount of vanilla CSS," which was true through the "Show author avatars" milestone but stopped scaling once vote widgets, follow buttons, and profile stat lines piled up. Kept the "no Node.js" spirit of the original plan by using Tailwind's standalone CLI instead of the conventional npm-based setup. The semantic-token approach (§5.3) turned out to pay for itself almost immediately: a full brand palette swap to "Cobalt Current" later on touched only two variable blocks, not any of the ~20 templates.
- **View transitions on the feed** (§5.3) — added once popularity-sorting made voting visibly reorder the feed; the browser's native cross-document View Transitions API was a better fit than hand-rolled JS reordering animation, given the project's server-rendered, JS-framework-free architecture.
- **The `games` app** (§5.4) — single-player and turn-based multiplayer games were never part of the original social-app scope at all; added as a distinct feature area with its own app, following the same "additive tables, existing patterns reused" approach as everything else in this section (`Match`/`SinglePlayerResult` are new tables, `games/logic/` mirrors `posts/markdown.py`, `games/stats.py` cross-imports into `ProfileView` the same way karma does).

## 10. Risks and open decisions

Comment-tree performance is still the main scaling caveat, addressed in §4 with a clear upgrade path (recursive CTE or django-mptt) if it's ever needed. Avatar storage on local disk is the other one — noted in the README, S3-compatible storage via `django-storages` is the drop-in fix if this deploys somewhere that isn't a single container. Static files are served by Django in dev; WhiteNoise remains the drop-in answer if this ever deploys for real. Games' turn-based design means there's no "it's your turn" notification beyond visiting the site — fine at this scale, but a natural future addition (email digest, or a browser push) if the games see real use.
