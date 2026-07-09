# Design Plan — "Chatter"

A social media web app built with Django. Users register (username/password or Google) after verifying their email, post in Markdown, comment with unlimited nesting, upvote/downvote posts and comments, follow each other, maintain a profile with an avatar, bio, and karma, and play simple games — both single-player and turn-based multiplayer — against each other. Everything runs in Docker with Postgres, and the Docker build doubles as the project's build test.

This document originally described a v1 plan and has been updated in place to describe what's actually built. §1–§8 describe the current system; §9 records what changed since the original v1 scope and why.

## 1. Goals and scope

The app delivers: user registration and login (username/password via Django's built-in auth, or "Continue with Google" via `django-allauth`), email verification gating username/password login, account settings for changing/setting a password and editing username/first/last name (§5.1b), user profiles (bio, avatar, join date, post/comment/follower/following counts, karma, game records) with a manual light/dark theme toggle, text posts on a public feed sorted by popularity with infinite scroll (§5.6), threaded comments with unlimited nesting, upvote/downvote on both posts and comments (with an automatic self-upvote on your own content and an animated re-sort when scores change), editing your own posts and comments with an "edited" marker (§5.5), a follow system with a "Following" feed alongside the main feed, private one-to-one direct messages between two users with an unread-count badge (§5.8), and a `games` app (Tic-Tac-Toe, Rock-Paper-Scissors, Connect Four, Checkers, Othello, Word Guess/Hangman, Wordle, 2048, Snake, and Doodle Jump — see §5.4). Posts and comments are authored in Markdown and render as formatted HTML when published (see §5.1). Pages are server-rendered with Django templates — no REST API, no JavaScript framework, and no Node.js anywhere in the stack (styling uses Tailwind CSS via its standalone CLI binary, not npm — see §5.3); the deliberate exceptions are 2048/Snake/Doodle Jump, where a real client-side game loop is unavoidable, and a handful of small, focused vanilla-JS enhancements (infinite scroll, match polling, the your-turn/unread-message badges — §5.6, §5.7, §5.8) that don't rise to needing a framework. The app is deployable for free to Render (Docker-native web hosting) + Neon (serverless Postgres) — see §6a.

Still out of scope: group messaging (direct messages are strictly one-to-one — §5.8), image embedding inside Markdown post/comment bodies (avatars are the only image upload), full-text search, moderation tools, and genuinely real-time multiplayer (games are turn-based/asynchronous by design, kept fresh with lightweight polling rather than a push channel — see §5.4, §5.7). The data model leaves room for these later without schema rewrites.

## 2. Tech stack

Python 3.12, Django 5.x, PostgreSQL 16 (official Docker image), psycopg 3 as the database driver, Gunicorn as the app server inside the container, and Django's template engine styled with Tailwind CSS (standalone CLI, no Node/npm — see §5.3). Markdown rendering uses `markdown-it-py` (CommonMark-compliant) with `nh3` for HTML sanitization. `django-allauth` provides Google OAuth alongside the built-in username/password auth. Email verification is hand-rolled (a signed, time-limited token via `django.core.signing`, not allauth's own email-confirmation flow — see §5.1a) since it only needs to gate the site's own registration form, not allauth's. `Pillow` backs the avatar `ImageField`. Dependencies are managed with `uv`: declared in `pyproject.toml`, locked in `uv.lock` (committed), so every environment — dev, Docker build, CI — installs the exact same versions with `uv sync`. Configuration (secret key, debug flag, database URL, Google OAuth credentials, SMTP settings) comes from environment variables so the same image works in dev and in build tests.

Three deployment-oriented dependencies were added alongside the Render/Neon work (§6a) without touching the local dev experience at all: `dj-database-url` parses Neon's single `DATABASE_URL` connection string into Django's `DATABASES` shape, `whitenoise` serves `collectstatic`'s output directly from the Gunicorn process (no separate static host), and `django-storages` provides an optional S3-compatible avatar backend for hosts with ephemeral disk. All three are no-ops in the Docker Compose/SQLite dev setup, which never sets `DATABASE_URL`/`DEBUG=0`/`AWS_STORAGE_BUCKET_NAME`.

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
├── .dockerignore                   # keeps .env and other dev-only files out of the build context/image
├── render.yaml                     # Render Blueprint - see §6a
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
│   ├── forms.py                    # RegistrationForm, ProfileForm, UserProfileForm, EmailVerifiedAuthenticationForm
│   ├── views.py                    # ...also PasswordChangeView - see §5.1b
│   ├── urls.py
│   ├── management/commands/seed_demo_data.py  # populates a fresh db with demo users/posts/games - see §6a
│   └── templates/accounts/         # login, register, profile, profile_edit, password_change, verification_*
├── posts/                          # posts, comments, voting, direct messages
│   ├── models.py                   # Post, Comment (both with an `edited` flag - see §5.5), PostVote,
│   │                                # CommentVote, Conversation, Message - see §5.8
│   ├── signals.py                  # auto-upvote own posts/comments
│   ├── markdown.py                 # render_markdown (markdown-it-py + nh3)
│   ├── ranking.py                  # rank_posts - weighted, time-decayed feed ranking
│   ├── forms.py                    # PostForm, CommentForm, CommentEditForm, MessageForm
│   ├── views.py                    # feed, following-feed, CRUD, editing, voting, messaging,
│   │                                # annotate_votes/toggle_vote/get_or_create_conversation
│   ├── context_processors.py       # unread_messages - powers the header badge, see §5.8
│   ├── urls.py
│   ├── templatetags/post_extras.py # {{ body|markdown }} filter
│   ├── static/posts/js/            # infinite_scroll.js (§5.6), unread_message_badge.js (§5.8)
│   └── templates/posts/            # feed, post_detail, post_form, _comment, _post_card/_post_list,
│                                    # _comment_list, conversation_list, conversation_detail
├── games/                          # single-player and turn-based multiplayer games
│   ├── models.py                   # Match (Tic-Tac-Toe/RPS/Connect Four/Checkers/Othello), SinglePlayerResult
│   ├── logic/                      # pure game-rule modules, no Django imports
│   │   ├── tic_tac_toe.py
│   │   ├── rock_paper_scissors.py
│   │   ├── connect_four.py
│   │   ├── checkers.py
│   │   ├── othello.py
│   │   ├── hangman.py
│   │   └── wordle.py
│   ├── stats.py                    # win/loss records, leaderboard queries, is_users_turn/your_turn_count
│   ├── context_processors.py       # your_turn_count - powers the header badge, see §5.7
│   ├── views.py
│   ├── urls.py
│   ├── static/games/js/            # 2048.js, snake.js, doodle_jump.js, checkers.js (move-selection helper),
│   │                                # match_poll.js, your_turn_badge.js - see §5.7
│   └── templates/games/            # hub, leaderboard, per-game play pages, _match_poll.html
├── static/css/
│   ├── input.css                   # Tailwind source (@theme, @layer base, view-transition opt-in)
│   └── tailwind.css                # compiled output, gitignored
└── templates/                      # base.html + shared partials
    ├── base.html                   # dark-mode bootstrap script (see §5.3)
    ├── _header.html                # nav + theme toggle + your-turn badge (§5.7) + unread-message badge (§5.8)
    ├── _avatar.html
    ├── _post_vote.html
    └── _comment_vote.html
```

Three apps keep concerns separated: `accounts` owns everything about users and the relationships between them, `posts` owns content and reactions to it, `games` owns the games and their scores. Django's built-in `User` model is used directly (the one decision flagged as irreversible in the original plan — confirmed before the first migration and never revisited).

## 4. Data model

Every model this app owns (`Profile`, `Follow`, `Post`, `Comment`, `PostVote`, `CommentVote`, `Match`, `SinglePlayerResult`) uses a `UUIDField(default=uuid.uuid4, editable=False)` primary key instead of Django's default auto-incrementing integer, so IDs are unguessable and non-enumerable in URLs (`/posts/<uuid>/`, not `/posts/1/`). `auth.User` itself was deliberately left out of this and still uses an integer PK — switching it would mean replacing Django's built-in user model with a custom one, which touches sessions, admin, and allauth's `SocialAccount` linkage and is explicitly the kind of decision Django warns against making mid-project; the tradeoff (User is the one model in this app whose numeric ID is exposed nowhere in a URL anyway) wasn't worth that risk. Converting existing integer PKs to UUIDs turned out to be impossible to express as a normal migration on Postgres — there's no valid cast from `bigint` to `uuid`, so `ALTER COLUMN id TYPE uuid` fails outright even against an empty table — so the `posts`/`accounts`/`games` migration histories were squashed to a single fresh `0001_initial` per app instead, which requires resetting any existing database (including in production) when deploying this change.

**User** — Django's built-in `auth.User` (username, password hash, email, joined date). Email is required at registration (`RegistrationForm` extends `UserCreationForm`); Google-created accounts get a real email from Google automatically.

**Profile** — one-to-one with User. Fields: `bio` (text, optional), `avatar` (`ImageField`, optional, capped at `MAX_AVATAR_UPLOAD_SIZE` — 2MB — validated in `ProfileForm.clean_avatar`), `email_verified` (bool, default `False`), `created_at`. Created automatically via a `post_save` signal on User (`accounts/signals.py`) — this covers both registration paths, since Google sign-in also creates a standard `User` row through the same manager. Accounts that existed before `email_verified` was added were grandfathered in as verified by a one-off data migration, so the gate only applies to registrations from that point on.

**Follow** — `follower` (FK → User, `related_name="following"`), `followed` (FK → User, `related_name="followers"`), `created_at`. A `UniqueConstraint` on `(follower, followed)` prevents duplicate follows; a `CheckConstraint` prevents self-follows at the database level, not just in the view.

**Post** — `author` (FK → User, `on_delete=CASCADE`), `body` (text, max ~5,000 chars), `edited` (bool, default `False` — see §5.5), `created_at`, `updated_at`. Default ordering is `-created_at`, but the feed itself orders by score (see §5).

**Comment** — `author` (FK → User), `post` (FK → Post, always set, even for nested replies), `parent` (FK → self, nullable; null means top-level), `body` (text), `edited` (bool, default `False` — see §5.5), `created_at`.

**PostVote** / **CommentVote** — both subclass an abstract `Vote` base (`user`, `value` — `+1`/`-1` via `Vote.UP`/`Vote.DOWN`, `created_at`) rather than a single generic-relation model, since there are only ever two votable types and duplicating a three-field model twice is simpler than `ContentType`/`GenericForeignKey` machinery. Each has a `UniqueConstraint` on `(user, post)` / `(user, comment)` — one vote per user per item, flipped or removed by voting again rather than accumulating rows.

Threading strategy (unchanged from v1): fetch all comments for a post in one query, build the tree in Python (`build_comment_tree`, a dict of `parent_id → children`). O(n), avoids recursive SQL.

**Conversation** — `user1`/`user2` (FK → User), `created_at`. Always stored with `user1_id < user2_id` (canonicalized in `get_or_create_conversation()`, not left to whichever order the two users happen to be passed in), so a `UniqueConstraint` on `(user1, user2)` can guarantee exactly one conversation per pair of users regardless of who messaged whom first - an unordered pair can't be uniqued directly. A `CheckConstraint` blocks messaging yourself, same pattern as `Match`'s self-challenge guard.

**Message** — `conversation` (FK → Conversation), `sender` (FK → User), `body` (text), `read` (bool, default `False`), `created_at`. `read` means "has the *other* participant read this" - a conversation only ever has two people, so there's no need for a per-recipient read-receipt table the way a group chat would need. See §5.8.

**Match** — one generic model for all five multiplayer games rather than a table per game, since Tic-Tac-Toe, Rock-Paper-Scissors, Connect Four, Checkers, and Othello all share an identical shape (2 players, one state blob, one winner) — unlike Post/Comment, which are genuinely different parent objects and justify `Vote`'s abstract-base-plus-subclass split above. Fields: `game` (`"ttt"`/`"rps"`/`"connect4"`/`"checkers"`/`"othello"`), `player1`/`player2` (FK → User), `state` (`JSONField`, game-specific shape — a 9-cell board array for Tic-Tac-Toe, a `{"choices": {...}}` map keyed by user ID for Rock-Paper-Scissors' simultaneous picks, a 6×7 nested array for Connect Four, an 8×8 nested array of `"r"`/`"b"`/`"R"`/`"B"` piece codes for Checkers, an 8×8 nested array of `"B"`/`"W"` piece codes for Othello), `status` (`"active"`/`"finished"`), `turn` (FK → User, nullable — null for Rock-Paper-Scissors, which has no "whose turn" concept), `winner` (FK → User, nullable; null on a finished match means a draw), timestamps. A `CheckConstraint` prevents challenging yourself. No constraint blocks multiple concurrent matches between the same two players (an immediate rematch is fine).

**SinglePlayerResult** — one row per completed single-player game. Fields: `player` (FK → User), `game` (`"hangman"`/`"2048"`/`"snake"`/`"doodle"`/`"wordle"`), `won` (bool), `score` (int), `created_at`. In-progress single-player state doesn't get a DB row: Hangman and Wordle use `request.session` (there's already a precedent for session-scratch-state in `accounts/views.py`'s `pending_verification_email`), and 2048/Snake/Doodle Jump are entirely client-side; a `SinglePlayerResult` is only written once a game actually ends. Snake and Doodle Jump have no natural win condition (both are endless score-chasers), so their `Finish` views always record `won=False` — score is the only meaningful signal, same as 2048's leaderboard ranking by high score rather than win count. Wordle's `score` is guesses-remaining-after-a-win (6 for a first-guess win, 1 for a last-guess win, 0 for a loss) rather than a flat win/loss flag like Hangman — framing it as "higher is better" lets it reuse the same descending-high-score leaderboard shape without inventing an ascending "fewest guesses" ranking.

Deletion policy (unchanged): deleting a user cascades to their posts, comments, votes, and follows.

## 5. URLs and views

| URL | View | Purpose |
|---|---|---|
| `/` | `FeedView` | All posts, ranked per the `?sort=` param — `default` (weighted, time-decayed karma blend, see §5.2), `top` (raw score), or `new` (recency) — paginated |
| `/following/` | `FollowingFeedView` | Same, filtered to authors the current user follows; login required |
| `/register/` | `RegisterView` | Signup form (username, email, password); sends a verification email instead of logging in |
| `/verification-sent/`, `/verify-email/<token>/`, `/resend-verification/` | `VerificationSentView`, `VerifyEmailView`, `ResendVerificationView` | Email verification flow — see §5.1a |
| `/login/`, `/logout/` | Django's built-in auth views, with a custom `AuthenticationForm` gating unverified accounts | |
| `/accounts/google/login/` | django-allauth | Google OAuth entry point, linked from login/register as "Continue with Google"; auto-links to an existing account with a matching email (`SocialAccountAdapter.pre_social_login`) instead of allauth's default conflict form |
| `/users/<username>/` | `ProfileView` | Bio, avatar, counts, karma, game records, recent posts and comments |
| `/settings/profile/` | `ProfileEditView` | Edit bio/avatar/username/first/last name; login required, always edits `request.user`'s own profile |
| `/settings/password/` | `PasswordChangeView` | Change or set a password — see §5.1b |
| `/users/<username>/follow/`, `/users/<username>/unfollow/` | `FollowView`, `UnfollowView` | POST only; login required |
| `/posts/new/` | `PostCreateView` | Login required |
| `/posts/<uuid>/` | `PostDetailView` | Post + paginated top-level comment tree (§5.6) + comment form |
| `/posts/<uuid>/edit/` | `PostEditView` | Author only (`UserPassesTestMixin`) — see §5.5 |
| `/posts/<uuid>/comment/` | `CommentCreateView` | POST only; optional `parent` field for replies |
| `/comments/<uuid>/edit/` | `CommentEditView` | POST only; author only — see §5.5 |
| `/posts/<uuid>/upvote/`, `/posts/<uuid>/downvote/` | `PostVoteView` | POST only; login required |
| `/comments/<uuid>/upvote/`, `/comments/<uuid>/downvote/` | `CommentVoteView` | POST only; login required |
| `/messages/` | `ConversationListView` | Inbox: the user's conversations, other participant, last message time, unread count — see §5.8 |
| `/messages/start/<username>/` | `StartConversationView` | POST only; get-or-creates the conversation and redirects into it |
| `/messages/<uuid>/` | `ConversationDetailView` | Participants only (403 otherwise); viewing marks the other participant's messages read |
| `/messages/<uuid>/send/` | `MessageSendView` | POST only; participants only (404 otherwise) |
| `/messages/unread-count/` | `UnreadMessageCountView` | JSON `{count}` — powers the header badge, see §5.8 |
| `/games/`, `/games/leaderboard/` | `GamesHubView`, `LeaderboardView` | Hub (your-turn/waiting matches, login required) and public leaderboard — see §5.4 |
| `/games/match/<uuid>/status/` | `MatchStatusView` | JSON `{updated_at, status}` for any of the 5 multiplayer games — powers `match_poll.js`, see §5.7 |
| `/games/your-turn-count/` | `YourTurnCountView` | JSON `{count}` — powers the header badge, see §5.7 |
| `/games/ttt/...`, `/games/rps/...`, `/games/hangman/...`, `/games/2048/...` | per-game challenge/play/move views | See §5.4 |

All write actions require login and CSRF; users can only edit their own content (enforced in the view, checked in tests). Post, Comment, PostVote, CommentVote, Match, and SinglePlayerResult all use UUID primary keys (§4), so every `<id>` above in a URL is a UUID, not a small integer.

### 5.1 Markdown rendering

Unchanged from v1: post and comment bodies are stored as raw Markdown, never rendered HTML. `markdown-it-py` (CommonMark plus fenced code blocks, tables, strikethrough, and linkify for bare URLs) converts to HTML, then `nh3` strips everything outside an allowlist of tags/attributes — this is what makes user-authored Markdown safe against `<script>` tags, `javascript:` hrefs, and event-handler attributes. Links get `rel="nofollow noopener"`. Rendered via a single `render_markdown` template filter shared by posts and comments. Still no image embedding via Markdown and no code syntax highlighting.

### 5.1a Email verification

Registering with username/password no longer logs the user in immediately: `RegisterView` emails a signed, expiring link (`django.core.signing`, 3-day max age via `EMAIL_VERIFICATION_MAX_AGE`) and redirects to a "check your email" page. Logging in is blocked until the link is visited — enforced in `EmailVerifiedAuthenticationForm.confirm_login_allowed` (`accounts/forms.py`), the officially-supported Django hook for exactly this kind of gate, rather than fighting with allauth's backend internals. `EMAIL_BACKEND` defaults to Django's console backend in dev (no `EMAIL_HOST` set), so links show up in the server log without needing real SMTP.

Google sign-in is exempt, since Google already verified the email: `accounts/signals.py` hooks allauth's `user_signed_up` signal (which only fires with a `sociallogin` kwarg for social accounts, never for the plain `RegisterView`) to mark those profiles verified immediately. Separately, `accounts/adapter.py`'s `SocialAccountAdapter.pre_social_login` looks up an existing user by the Google-provided email *before* allauth decides whether to show its own signup form, and connects the login to that existing account if one matches — treating a Google-verified email as proof of ownership rather than showing allauth's default (unstyled) conflict-resolution form.

### 5.1b Account settings

`/settings/profile/` (`ProfileEditView`) edits `Profile` (bio/avatar) and `User` (username/first/last name) together, one submit for both — `UserProfileForm` binds to a *fresh copy* of the `User` row fetched by primary key, not `request.user` directly, because Django's `ModelForm` writes submitted values onto its bound instance during validation *before* a uniqueness check can fail it. Binding `request.user` itself meant a rejected duplicate-username submission would leak the not-yet-saved, rejected username onto the same object `_header.html`'s nav link reads from, pointing "Log out"'s neighbor at a different real user's profile for the rest of that one response — a real bug caught by testing the duplicate-username path specifically, fixed by giving the form its own copy to mutate.

`/settings/password/` (`PasswordChangeView`) picks between Django's `PasswordChangeForm` (requires the current password) and `SetPasswordForm` (no current-password check) based on `request.user.has_usable_password()` — Google-only signups get an unusable password from allauth, so they'd never be able to satisfy `PasswordChangeForm`'s check otherwise. `update_session_auth_hash` keeps the session logged in afterward, same as Django's own built-in password-change view does.

### 5.2 Voting and karma

Clicking a vote arrow toggles it: clicking the same direction again removes the vote, clicking the opposite direction flips it (`toggle_vote` in `posts/views.py`). A `post_save` signal (`posts/signals.py`, guarded on `created=True`) automatically gives every new post and comment a self-upvote from its author — this fires regardless of how the row is created (view, admin, shell), not just through `PostCreateView`/`CommentCreateView`.

Score and "did the current user vote, and which way" are computed via `annotate_votes()`, shared across the feed, post detail, and profile post/comment lists: `Coalesce(Sum("votes__value"), 0)` for score, a correlated `Subquery` against the vote table for the current user's vote direction. One gotcha worth documenting: aggregation via `.annotate()` silently drops a queryset's ordering (explicit or the model's default `Meta.ordering`) from the generated SQL, so `annotate_votes()` re-captures and reapplies whatever ordering was present beforehand.

Karma on the profile page is the sum of vote values across all of a user's posts and comments (two aggregate queries, `PostVote`/`CommentVote` filtered by `post__author`/`comment__author`).

The feed is no longer sorted by raw post score. `posts/ranking.py`'s `rank_posts()` blends four signals with tunable weights (`POST_KARMA_WEIGHT=1.0`, `COMMENT_KARMA_WEIGHT=0.5`, `POSTER_KARMA_WEIGHT=0.1`): the post's own karma, the karma earned by its comment thread, and the poster's overall karma (their total across all posts and comments, profile-page karma reused as-is) — then decays the weighted total by the post's age using a Hacker News-style `weighted_karma / (age_hours + 2) ** GRAVITY` formula (`GRAVITY=1.8`), so a post's rank fades over time even if its karma never changes and a recent post can outrank an older, higher-karma one once it's aged enough.

This runs in Python after a single fetch rather than as one big `annotate()`, deliberately: summing two different reverse relations (`PostVote` and `CommentVote`, reached via two different join paths from `Post`) in the same `annotate()` call causes a join fan-out that silently inflates both sums — a sharper version of the ordering gotcha above. `rank_posts()` sidesteps it with separate grouped-aggregate queries (comment karma per post, post/comment karma per author) merged into Python, then sorts the fetched page's posts by the computed score. The trade-off: ranking is recomputed over every matching post on each feed load rather than pre-sorted at the database level — proportionate at this app's scale, but worth revisiting (e.g. a cached/precomputed rank) if post volume grew substantially (see §10).

The default ranking isn't the only option: a `?sort=` query param (`FeedView.get_sort()`, whitelisted against `{"default", "top", "new"}`, falling back to `"default"` for anything else) switches between it, `top` (`order_by("-score", "-created_at")` — the plain popularity ordering the feed used before ranking existed), and `new` (`order_by("-created_at")`, ignoring votes entirely). `feed.html` exposes this as a second pill-button row next to the All/Following tabs, and both the feed-type links and pagination links carry the current `sort` value forward so switching feeds or pages doesn't silently reset it back to `default`.

### 5.3 Styling

Tailwind CSS, via the [standalone CLI binary](https://tailwindcss.com/blog/standalone-cli) rather than a Node/npm toolchain — the Dockerfile downloads a pinned, architecture-aware binary the same way it already vendors the `uv` binary, so the stack stays Python-only. Source is `static/css/input.css`; compiled output is `static/css/tailwind.css` (gitignored, generated). Markdown-rendered post/comment bodies use the bundled `@tailwindcss/typography` plugin (the `prose` class) instead of hand-styling arbitrary HTML — the standalone CLI ships the official first-party plugins without needing npm. The reply/edit-toggle "checkbox hack" uses Tailwind's named `peer`/`peer-checked` variants (`peer/reply`, `peer/edit` — see §5.5), so a comment showing both toggles at once doesn't have one checkbox's state leak into the other's form.

The color system ("Cobalt Current" — cobalt blue brand, amber upvotes, rose downvotes, emerald karma) is a set of semantic tokens (`--bg`, `--surface`, `--fg`, `--accent`, ...) defined once on `:root` and remapped under `.dark`, then exposed to Tailwind via `@theme { --color-bg: var(--bg); ... }` — templates use `bg-surface`, `text-accent`, etc. throughout rather than raw Tailwind colors or `dark:` variants, so a full palette swap (as happened once already, from an earlier violet/indigo palette) only touches the two variable blocks in `input.css`, never the ~20 templates that reference them. Dark mode is class-based (`@custom-variant dark (&:where(.dark, .dark *));`) rather than Tailwind's `prefers-color-scheme` default, since the header's sun/moon toggle button needs to override the OS preference and persist the choice — a blocking inline script in `base.html`'s `<head>` (before the stylesheet paints) applies `.dark` from `localStorage`, falling back to `prefers-color-scheme` only on a first visit, which avoids a flash of the wrong theme that a deferred/post-paint script wouldn't.

The comment form is inline per-comment rather than a single shared form at the bottom of the page: each comment has its own collapsible reply form, expanded via a hidden checkbox and a `<label>`, with no JavaScript — matching the "no JS framework" goal while avoiding the earlier design's jump-to-bottom-of-page UX.

Voting redirects back to a full page reload with posts re-sorted by score, which would otherwise just snap to the new order. `input.css` opts every navigation into the browser's native cross-document View Transitions API (`@view-transition { navigation: auto; }` — Chrome/Edge 126+, a harmless no-op elsewhere), and `feed.html` gives each post card a stable `view-transition-name` (`post-<id>`), so the browser matches a card across the old and new page and animates it sliding to its new rank instead of jumping. No custom JS.

### 5.4 Games

The `games` app adds Tic-Tac-Toe, Rock-Paper-Scissors, Connect Four, Checkers, and Othello (turn-based multiplayer, challenged from a profile page like the Follow relationship — no open lobby, no accept/decline handshake), Word Guess/Hangman and Wordle (single-player, session-based), and 2048, Snake, and a Doodle Jump clone (single-player, client-side).

Multiplayer is explicitly **turn-based/asynchronous, not real-time** — a deliberate choice to avoid adding Channels/an ASGI server/a Redis channel layer for a feature that doesn't need them. A move is a normal POST + redirect; the opponent sees it next time they load the page. `games/views.py`'s `GamesHubView` groups a player's active matches into "your turn" vs "waiting on opponent" so discovering a pending move doesn't require a notification system. Concurrent move submissions (mainly a concern for Rock-Paper-Scissors, where both players can legitimately move at once) are handled with `select_for_update()` inside `transaction.atomic()`, re-checking `status`/`turn` after acquiring the lock — not a queue or external lock, which would be over-engineering at this scale.

Game rules live in `games/logic/` as pure Python functions with no Django imports (mirroring `posts/markdown.py` as the precedent for keeping rules separate from the view/model layer), directly unit-tested without touching the database. Connect Four's win detection scans all four line directions from every occupied cell. Checkers uses a deliberately simplified ruleset (diagonal moves only, captures optional rather than forced, single jump per turn, kings move any diagonal direction) rather than standard American forced-capture rules — a non-king piece can still capture backward even though it can't simple-move backward, the standard convention, documented explicitly in the module since the simplified spec left it open; there's no draw concept since the lack of forced captures means no mutual-stalemate deadlock, only a one-sided "no legal moves" loss. Checkers' move UX is inherently two clicks (select a piece, then a destination), handled by a small vanilla-JS click helper (`checkers.js`) that fills two hidden form fields and submits — simpler than tracking a "selected piece" in server-side session state, and consistent with the project's "interaction logic in JS, server stays a dumb state-transition validator" split.

Othello is the one game where turn order isn't strict alternation: a move must flip at least one opponent piece (`games/logic/othello.py`'s `_flips_for_move` scans all 8 directions, collecting a contiguous opponent run and only committing the flip if it terminates on the mover's own color before the board edge or an empty cell), and a player with no legal move must pass back to their opponent rather than the game ending — it only ends once *neither* player has a legal move, with the winner decided by piece count. `next_turn_state(state, mover, opponent)` centralizes this as a single three-way decision (`"continue"`/`"pass"`/`"game_over"`), mirroring how `checkers.check_winner(state, next_player)` already centralizes a similar "is the next player stuck" check, so the view only has to translate the result into a `Match.turn`/`status`/`winner` update. The one UX wrinkle: a player can legitimately see "Your turn" twice in a row if their opponent just passed, so the match template derives a `just_passed` flag (opponent currently has zero legal moves) to show "so-and-so had no legal move and passed" instead of a bare turn banner.

2048, Snake, and Doodle Jump are the exceptions to "no client-side game logic": their rules live entirely in `games/static/games/js/`, vanilla JS game loops, since real-time gameplay can't be a server round-trip per move. 2048 implements all four slide directions with a single "slide left" routine plus a rotate-and-rotate-back trick; each power-of-two tile value gets its own shade by cycling through the theme's four semantic accent colors (§5.3) — blue, amber, rose, green, back to solid blue at 4096 — rather than the two flat color bands it originally shipped with, which left every tile below 64 rendered as `bg-surface-hover`, identical to the board's own background and effectively invisible. Snake uses a DOM grid re-rendered each tick (`setTimeout` chaining so the tick rate can speed up as the snake grows). Doodle Jump is the app's first `<canvas>`-based game, using `requestAnimationFrame` for continuous gravity/jump physics with static scrolling platforms (no moving/breakable platforms or enemies — kept to a simple MVP). All three POST just a final score (2048 also sends the highest tile reached) to a `FinishView` at game over; the server does bounds-checking (sane ranges, and for 2048 a power-of-two tile check consistent with the score) rather than full move-replay validation, proportionate to a casual game's stakes.

Wordle (`games/logic/wordle.py`) follows Hangman's session-based pattern instead — no client-side JS, since a whole-word guess is naturally a single form submission. `apply_guess` does a two-pass comparison against the target: an exact-match pass marks correct letters and removes them from a per-letter count pool built from the target, then a second pass marks remaining guess letters "present" only while the pool still has that letter available, else "absent" — the classic fix for duplicate-letter guesses (e.g. guessing "apple" against target "grape" correctly marks only the first of the two guessed P's "present", since "grape" has just one). Unlike Hangman's always-valid `apply_guess` (invalidity is filtered before the call), Wordle's raises `InvalidMove` for a guess that isn't a 5-letter word in its own `WORD_LIST` — the same list doubles as the valid-guess dictionary, proportionate scope rather than maintaining a separate larger dictionary.

`games/stats.py` centralizes the win/loss/high-score queries so both `ProfileView` (which cross-imports from `games`, mirroring the existing precedent of importing from `posts` for karma) and the public `/games/leaderboard/` page read from the same source rather than duplicating aggregation logic. `is_users_turn(match, user)` is the one non-obvious piece of this: it's not a plain `match.turn_id == user.id` check for every game, since Rock-Paper-Scissors has no `match.turn` at all (both players choose simultaneously — §4) and "your turn" there instead means "you haven't locked in a choice yet." `GamesHubView`'s own your-turn/waiting split had exactly this bug before `is_users_turn` was centralized (every active RPS match landed in "waiting" regardless of whether the viewer had actually picked yet); it and the your-turn badge (§5.7) both now call the same helper so they can't disagree with each other.

### 5.5 Editing posts and comments

Both `Post` and `Comment` carry an `edited` boolean (§4), shown as "· edited" next to the timestamp. This is a plain flag set explicitly in the edit views rather than something inferred by comparing `created_at`/`updated_at` — `auto_now_add` and `auto_now` are each stamped independently at save time, so on a brand-new row they can differ by a sub-millisecond amount, which would have produced false "edited" markers on posts nobody ever touched. The flag only flips when `form.has_changed()` is true, so resubmitting a form with unchanged content doesn't mark it edited either.

`PostEditView` already existed as a plain `UserPassesTestMixin` + `UpdateView` before this; it just had no link pointing at it anywhere in the templates. Comments get the same author-only editing from scratch, but as a `CommentEditView(LoginRequiredMixin, View)` mirroring `CommentCreateView`'s POST-only shape (404 for a non-author, rather than pulling in `UserPassesTestMixin`) since there's no GET-rendered page of its own — editing happens inline, via the same checkbox+`<label>` CSS-toggle trick `_comment.html` already used for Reply (§5.3). Because a comment can now show both a Reply toggle and an Edit toggle at once, both switched to Tailwind's *named* peer modifiers (`peer/reply`, `peer/edit` and their matching `peer-checked/reply:`/`peer-checked/edit:`) instead of a single unnamed `peer` — with two same-level checkboxes sharing one unnamed peer class, checking either one would reveal both forms.

### 5.6 Infinite scroll

The feed and a post's comment thread both now render only the first 6 items (`POSTS_PAGE_SIZE`/`COMMENTS_PAGE_SIZE` in `posts/views.py`) and load more as the user nears the bottom, replacing the feed's old Previous/Next pager outright. One small generic script, `posts/static/posts/js/infinite_scroll.js`, drives both: it watches a `[data-infinite-scroll-sentinel]` element via `IntersectionObserver` and, once it's within `rootMargin: "300px"` of the viewport, fetches `data-next-url` with an `X-Requested-With: XMLHttpRequest` header and inserts the JSON response's `html` field just before itself, then updates its own `data-next-url` from the response's `next_url` (or removes itself once that's `null`). Neither view needed a new URL for this — `FeedView.render_to_response` and `PostDetailView.get` both just branch on that header and return `JsonResponse({"html": ..., "next_url": ...})` instead of the normal template response, reusing `FeedView`'s existing `paginate_by`/`page_obj` machinery for posts.

Comments paginate differently: over the already-built comment tree in Python, not the underlying queryset, because a top-level comment's replies have to stay attached to it no matter how deep the thread goes, and a query-level `OFFSET`/`LIMIT` over just top-level rows can't also express "and every descendant of these particular rows" without a recursive query. Given this app's comment trees are small, rebuilding the full tree per page is the same proportionate tradeoff `annotate_votes()` already makes by recomputing on every load instead of precomputing (§5.2).

One bug this surfaced: the sentinel element originally lived as a *sibling* of `#post-list`/`#comment-list` rather than inside it, so items inserted just before it landed outside those containers — outside the reach of `space-y-4`'s margin and `divide-y`'s border, both of which only apply to direct children of the element they're declared on. Fixed by nesting the sentinel as the last child of each container instead.

### 5.7 Keeping multiplayer matches fresh

Multiplayer is still turn-based/asynchronous, not real-time (§5.4) — these two additions make "it became your turn" visible without a real push channel, not full real-time gameplay. `games/static/games/js/match_poll.js` runs on every match page: it polls the generic `/games/match/<uuid>/status/` endpoint (`MatchStatusView`, one view for all 5 multiplayer games, since the client only ever needs "has anything changed since I loaded this page") every 3 seconds, and reloads the page outright if the returned `updated_at` differs from what was rendered at load time — the simplest correct way to show an opponent's move without needing to know how to patch the board's DOM for 5 different games.

The header's Games link also carries a live count badge (`games/context_processors.py`'s `your_turn_count`, added to every page's context so it works from anywhere in the site, not just the games hub) of how many active matches are waiting on the viewer's move. `games/static/games/js/your_turn_badge.js` polls `/games/your-turn-count/` every 10 seconds and updates the badge's text/visibility in place — deliberately *not* a page reload like `match_poll.js`, since a global badge reloading the whole site every 10 seconds on every page would be far more disruptive than a single match page doing it only while that one match is still active.

### 5.8 Direct messages

Private one-to-one messaging, added under the `posts` app rather than a new app (posts already owns "content and reactions to it," and a DM is close enough in shape - author, body, timestamp - to fit that umbrella without a fourth top-level app). A "Message" button on another user's profile (`accounts/templates/accounts/profile.html`, alongside Follow/Challenge, hidden on your own profile) POSTs to `StartConversationView`, which resolves the conversation via `get_or_create_conversation()` and redirects straight into it - clicking Message a second time reopens the same thread rather than starting a new one, thanks to `Conversation`'s canonicalized `(user1, user2)` ordering (§4).

Privacy is enforced the same way `PostEditView`/`CheckersMatchView` already enforce authorship: `ConversationDetailView` is a `UserPassesTestMixin` `DetailView` whose `test_func` checks `request.user.id in (conversation.user1_id, conversation.user2_id)`, returning 403 for anyone else (checked directly by test, not just implied by "well the view filters it out"). `MessageSendView` does the equivalent check as a plain 404, mirroring `CommentCreateView`'s POST-only, no-GET-page style rather than pulling in the mixin, consistent with how `CommentEditView` made the same call (§5.5).

The header's "Messages" link carries the same live-badge treatment as the your-turn badge (§5.7): `posts/context_processors.py`'s `unread_messages` makes the count available on every page, and `unread_message_badge.js` polls `/messages/unread-count/` every 10 seconds and updates it in place. One deliberate difference from the your-turn badge: that one disappears entirely at zero, but the Messages link itself always stays visible regardless of count - unlike the games hub (reachable via the always-present "Games" link either way), there'd be no way to open your inbox at all once it hit zero unread if the badge were the only entry point. `ConversationDetailView.get()` marks the other participant's unread messages read *before* building the response context, not after, so this same page load's own badge count already reflects the read state it just caused, rather than showing a stale count until the next page.

Message bodies use the same Markdown pipeline as posts/comments (`{{ message.body|markdown }}`, §5.1), not a separate one. The one wrinkle a chat bubble adds that an article body doesn't: `conversation_detail.html` colors sent/received bubbles with `bg-accent`/`bg-surface-hover` backgrounds and a matching text color, but the `prose` typography plugin sets its own text-color CSS variables on headings, links, and code regardless of the bubble's color - left alone, a Markdown link in a sent message would render in the theme's global link color (`--color-accent`), i.e. accent-colored text on an accent-colored bubble, unreadable. Fixed with an arbitrary-variant override (`[&_a]:text-inherit [&_*]:text-inherit`) that forces every element `prose` touches back to the bubble's own inherited text color instead.

## 6. Docker setup

Two services in `docker-compose.yml`, unchanged in shape from v1:

**db** — `postgres:16`, credentials from `.env`, a named volume, a healthcheck so the app waits for a ready database.

**web** — built from the project `Dockerfile`. Base image `python:3.12-slim` with `curl`/`ca-certificates` installed (needed to fetch the Tailwind CLI binary — see §5.3), the `uv` binary copied from `ghcr.io/astral-sh/uv`, and the Tailwind CLI binary downloaded for the build's `$TARGETARCH` (`amd64`/`arm64`). Dependency install is its own cached layer (`uv sync --frozen --no-dev`) so code changes don't re-trigger it; the Tailwind CSS build runs after the source is copied in (`RUN tailwindcss -i ... -o ... --minify`), followed by `collectstatic --ignore=input.css` baked into the image at build time rather than run on every container start (deterministic given everything above it, so redoing it on every boot would just be repeated work in front of Gunicorn for no benefit — `input.css`, the Tailwind *source*, is excluded because its `@import "tailwindcss"` line isn't a real file reference and WhiteNoise's manifest post-processor errors trying to resolve it as one). The container runs as a non-root user. `docker-entrypoint.sh` runs `migrate`, then either `runserver` with a background `tailwindcss --watch` process (when `DEBUG=1`, so editing a template's classes recompiles the CSS live) or Gunicorn directly with `--no-control-socket` (Gunicorn 25.1+'s runtime-management socket defaults to `$HOME/.gunicorn/`, which fails with a permission error for the "app" user — a homeless system account with no home directory — since nothing here uses the separate `gunicornc` CLI that socket exists for anyway). The compose file bind-mounts the source directory in dev.

`.env.example` documents every variable, including `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` (see the README for how to obtain them) and the optional Render/Neon/S3 ones (§6a); the real `.env` is gitignored, as is `media/` (uploaded avatars) and the compiled `tailwind.css`. `.dockerignore` mirrors `.gitignore` — its absence was a real gap fixed alongside the Render work: without it, `COPY . .` would bake a local `.env` (secrets, and whatever `DEBUG` value happened to be set locally) straight into the image.

Daily workflow is unchanged: `docker compose up`, `docker compose run --rm web python manage.py <cmd>` for one-offs, `uv add <package>` + rebuild for new dependencies. Working outside Docker (`uv sync` + `manage.py runserver`) falls back to SQLite when `POSTGRES_DB` isn't set — but the Tailwind CLI has to be run separately in that case (fetched once, run in `--watch` mode alongside `runserver`; see the README). `manage.py seed_demo_data` (`accounts/management/commands/`) populates a fresh, empty database with demo users, posts, comments, votes, follows, and a spread of game/leaderboard history in one command — useful after a reset like the one the UUID migration required (§4), or for spinning up a new environment that would otherwise be empty; it's idempotent (skips with a warning if any `Post` already exists) rather than doing real per-row upsert logic, so reseeding a populated database is a no-op instead of risking duplicate spam.

### 6a. Deploying to Render + Neon

The app is deployable for free without any code forking: **Render** runs the existing `Dockerfile` directly as a Docker-native web service, and **Neon** provides serverless Postgres — both have generous, non-time-limited free tiers, unlike most "free trial" hosts. `render.yaml` is a Blueprint that provisions the web service and generates `SECRET_KEY` automatically; `DATABASE_URL`, `ALLOWED_HOSTS`, and the optional email/OAuth/S3 vars are all `sync: false` (secrets or values Render can't know upfront, filled in via its dashboard instead — see the README's step-by-step).

A few settings exist purely to make this work correctly rather than just "work":

- `dj_database_url.parse(..., conn_max_age=0, ssl_require=True)` for `DATABASE_URL` — `conn_max_age=0` (no persistent connections) is deliberate, not an oversight: Neon's commonly-copied connection string routes through PgBouncer in transaction-pooling mode, and Django holding a connection open across requests on top of that can surface as "prepared statement already exists" errors or session state leaking across unrelated requests.
- `IS_RENDER` (from Render's auto-injected `RENDER=true` env var) gates `SECURE_SSL_REDIRECT`/`SECURE_PROXY_SSL_HEADER`/HSTS specifically, rather than gating them on `DEBUG=False` the way the generic cookie-security settings are. The distinction matters: "definitely behind Render's TLS-terminating edge" and "`DEBUG=0` for some other reason" aren't the same thing, and forcing an HTTPS redirect with no HTTPS listener actually in front (e.g. `DEBUG=0` used locally) would make the app completely inaccessible.
- Avatar storage defaults to local disk, which doesn't survive a redeploy on Render's free tier (ephemeral disk). Setting `AWS_STORAGE_BUCKET_NAME` (plus the matching key/secret/endpoint vars) switches `STORAGES["default"]` to `django-storages`' S3 backend, which also works against any S3-compatible host (Cloudflare R2, Backblaze B2) via `AWS_S3_ENDPOINT_URL` — left unset by default so local dev and single-container deploys keep the simpler disk backend.
- `ALLOWED_HOSTS` can't be known before the first deploy (Render assigns the hostname), so it's `sync: false` and the README documents setting it *after* first deploy — until then, Django rejects every request including Render's own health check with a 400, which is expected and self-resolves once it's set.

Both Render's free web service and Neon's free compute spin down/autosuspend after a period of inactivity, so the first request after a quiet period pays a cold-start delay — this doesn't affect correctness, just documented as an expectation in the README.

## 7. Build and test verification

Unchanged in mechanism: `docker compose build` must succeed from a clean checkout, `docker compose up` must produce a working app, and `docker compose run --rm web python manage.py test` runs the suite against a throwaway Postgres database. `./scripts/build-test.sh` chains build → up db → migrate → test → `check --deploy` into one command.

Test coverage has grown alongside the feature set (278 tests as of this writing) — registration (including the required-email field and email verification gate), Google-account auto-profile-creation and email-matched account linking, auth-gating, post/comment CRUD/editing and permissions, comment tree construction and pagination (including that a reply to an already-shown thread stays nested rather than arriving as an orphan on a later page), infinite-scroll JSON responses for both the feed and comments, Markdown rendering and XSS-stripping, follow/unfollow (including the self-follow and duplicate-follow constraints), voting (toggle/flip/remove, anonymous rejection, score aggregation), the automatic self-upvote signal, karma computation, feed ranking (the tied-score/newest-first tiebreak, the score-first primary sort, isolating each new factor in turn — comment karma, poster karma, and time decay overriding raw score for an old post — and the `top`/`new` sort overrides ignoring decay/karma respectively), account settings (password change/set for both usable- and unusable-password accounts, username/name editing including the duplicate-username-leaking-onto-request.user regression), direct messages (conversation canonicalization regardless of who messaged first, the self-conversation `CheckConstraint`, participant-only access on both viewing and sending, the read/unread transition on viewing, and the inbox's per-conversation unread counts), and the `games` app (pure game-logic unit tests per game, full match flows through the views including turn enforcement and win/draw resolution, the match-status/your-turn-count endpoints, the RPS-specific `is_users_turn` special case, session-based Hangman/Wordle state, 2048 score-submission bounds-checking, and leaderboard/profile-stat accuracy).

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
- **Time-decayed, karma-weighted feed ranking** (`posts/ranking.py`, §5.2) — the original feed ordering was pure `(score desc, created_at desc)`, so a popular post from months ago could sit at the top forever. Replaced with a Hacker News-style formula blending post karma, comment-thread karma, and poster karma, decayed by post age, so the feed favors what's currently good rather than what was ever good. A `?sort=` param (`default`/`top`/`new`) lets a reader opt back into the plain popularity or pure-recency orderings if they prefer.
- **Othello and Wordle** — the `games` app's second expansion after Connect Four/Checkers/Snake/Doodle Jump, following the identical pattern (new `Match`/`SinglePlayerResult` choice codes, a `games/logic/` module, the same view triads). Othello introduced the app's first non-strict-alternation turn order (a pass mechanic) and Wordle its first raising `apply_guess` (dictionary validation living in the logic module rather than the view) — see §5.4.
- **Free deployment to Render + Neon** (§6a) — the original plan only ever targeted local Docker Compose. Made the app deployable without a rewrite: `dj-database-url`/WhiteNoise/optional `django-storages` for the pieces a single-container Compose setup didn't need, a `render.yaml` Blueprint, and a handful of settings (`IS_RENDER`, `conn_max_age=0`) that only matter once something other than a bind-mounted dev container is involved.
- **UUID primary keys** (§4) — requested as a standalone hardening pass, not tied to any feature. Every app-owned model switched from Django's default auto-incrementing integer PK to a `UUIDField`; `auth.User` was deliberately left as-is (§4). Required squashing three apps' migration histories to fresh initial migrations rather than an in-place `AlterField`, since Postgres has no `bigint`→`uuid` cast — discovered by actually trying it, not anticipated up front.
- **Account settings: password change/set, username/name editing** (§5.1b) — neither existed before; added as a natural pair alongside the existing profile-edit page. Surfaced one real bug (a duplicate-username submission leaking onto `request.user`, §5.1b) that only showed up once the two edits (profile fields + account fields) were combined into one form.
- **Editing posts and comments** (§5.5) — `PostEditView` had existed since early on but was never actually reachable from any template; comments got the equivalent capability from scratch, plus the "edited" marker for both.
- **Infinite scroll on the feed and comment threads** (§5.6) — replaced the feed's manual pager and comments' load-everything-at-once approach with the same scroll-triggered pagination mechanism for both.
- **Match polling and the your-turn badge** (§5.7) — closed the gap where a multiplayer opponent's move was invisible until the next manual page load; still asynchronous/turn-based under the hood (§5.4), just with lightweight polling making the asynchrony less noticeable.
- **`manage.py seed_demo_data`** (§6a) — added once the UUID migration's database reset made "start from a genuinely empty database" a real, recurring situation rather than a one-time setup step.
- **Direct messages** (§5.8) — explicitly out of scope in the original v1 and still called out as out of scope for *group* messaging; one-to-one DMs added under the `posts` app rather than a new app, reusing the same participant-only-access and live-badge patterns already established by multiplayer matches (§5.4) and the your-turn badge (§5.7) instead of inventing new ones.

## 10. Risks and open decisions

Comment-tree performance is still the main scaling caveat, addressed in §4 with a clear upgrade path (recursive CTE or django-mptt) if it's ever needed — infinite scroll (§5.6) caps how much of the tree renders per request, but still rebuilds the *entire* tree in Python on every page fetched, so it doesn't reduce the underlying query/build cost for a post with a huge thread, only the render cost. Avatar storage on local disk is the default — noted in the README, S3-compatible storage via `django-storages` is the drop-in fix (§6a) if this deploys somewhere with ephemeral or multi-instance disk. Static files are served by Django in dev; WhiteNoise handles it in production (§6a). Games' turn-based design means there's still no notification beyond visiting the site or having a match page open (§5.7's polling only helps once you're already looking at the relevant page) — a natural future addition (email digest, or a browser push) if the games see real use; match/badge polling also means every open match page and every page load makes a small recurring background request, fine at this app's scale but worth revisiting (e.g. WebSockets/SSE) if concurrent active matches grew large. Feed ranking (§5.2) recomputes over every matching post in Python on each load rather than pre-sorting at the database level, to avoid a join-fan-out bug that a single cross-relation `annotate()` would hit — fine at this app's post volume, but would need a cached/precomputed rank (e.g. a periodic job writing a `rank_score` column) if post counts grew much larger. UUID primary keys (§4) trade a small amount of index/storage overhead and non-sequential insert locality for unguessable, non-enumerable URLs — the right tradeoff at this app's scale, and Postgres's native `uuid` type keeps the overhead modest (16 bytes, not a 36-character string). Direct messages (§5.8) are strictly one-to-one by design, not a stepping stone toward group chat - `Conversation`'s two-FK shape and `Message.read`'s single boolean both assume exactly two participants and would need a real rework (a participants M2M, per-recipient read receipts) rather than a small extension if group messaging were ever added. The unread-message badge adds one more small recurring background request per page load on top of the your-turn badge's (§5.7) - fine at this app's scale, same caveat as that one about revisiting if it ever needed to scale further.
