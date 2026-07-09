from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Follow, Profile
from games.logic import checkers, connect_four, othello, tic_tac_toe
from games.models import Match, SinglePlayerResult
from posts.models import Comment, CommentVote, Post, PostVote

DEMO_PASSWORD = "demo-pass-1234"

USERS = [
    # username, email, is_superuser, bio
    ("admin", "admin@example.com", True, "Running the show around here."),
    ("matt", "matt@example.com", False, "Building Chatter. Ask me anything."),
    ("alice", "alice@example.com", False, "Coffee, code, and cats."),
    ("bob", "bob@example.com", False, "Backend engineer. Postgres enthusiast."),
    ("carol", "carol@example.com", False, "Photographer chasing golden hour."),
    ("dave", "dave@example.com", False, "Refactoring is my cardio."),
    ("erin", "erin@example.com", False, "Commit early, commit often."),
]

# (author, body, hours_ago) - hours_ago backdates created_at so the feed
# doesn't show every post as posted in the same instant.
POSTS = [
    ("admin", "I'm the admin and you gotta deal with it", 30),
    ("matt", "My first post\n\nHello, **world**! Excited to get this thing running.", 28),
    ("alice", "My morning routine\n\nCoffee, a short walk, then _deep work_ until noon.", 26),
    ("bob", "Just shipped a major refactor. Feeling good.", 24),
    ("carol", "Sunset photos from last night's trip.", 20),
    ("dave", "Anyone else's Monday feel like *this*?", 16),
    ("erin", "PSA: commit early, commit often. Future you will thank you.", 12),
    ("bob", "TIL you can use `EXPLAIN ANALYZE` to debug slow Postgres queries.", 8),
    ("alice", "Reading recommendations? Looking for something sci-fi.", 4),
]

# (post_index, author, body, parent_body_or_None) - parent_body looks up an
# already-created comment on the same post by its body text, to nest a reply.
COMMENTS = [
    (1, "alice", "Welcome! Great to have this up and running.", None),
    (1, "bob", "Congrats on the launch!", None),
    (3, "erin", "What was the refactor?", None),
    (3, "bob", "Mostly collapsing three near-duplicate views into one.", "What was the refactor?"),
    (7, "carol", "Ha, EXPLAIN ANALYZE has saved me more times than I can count.", None),
    (8, "carol", "Try Project Hail Mary if you haven't already.", None),
    (8, "dave", "Seconding that recommendation.", "Try Project Hail Mary if you haven't already."),
]

FOLLOWS = [
    ("alice", "bob"),
    ("dave", "matt"),
    ("erin", "carol"),
]


class Command(BaseCommand):
    help = "Populates the database with demo users, posts, comments, votes, and game history."

    def handle(self, *args, **options):
        if Post.objects.exists():
            self.stdout.write(self.style.WARNING("Posts already exist - skipping seed to avoid duplicates."))
            return

        users = self._create_users()
        posts = self._create_posts(users)
        self._create_comments(posts, users)
        self._create_votes(posts, users)
        self._create_follows(users)
        self._create_game_history(users)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(users)} users and {len(posts)} posts."))
        self.stdout.write(f"All demo accounts share the password: {DEMO_PASSWORD}")

    def _create_users(self):
        users = {}
        for username, email, is_superuser, bio in USERS:
            user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
            user.email = email
            user.is_staff = is_superuser
            user.is_superuser = is_superuser
            user.set_password(DEMO_PASSWORD)
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.bio = bio
            profile.email_verified = True
            profile.save(update_fields=["bio", "email_verified"])
            users[username] = user
        return users

    def _create_posts(self, users):
        now = timezone.now()
        posts = []
        for author, body, hours_ago in POSTS:
            post = Post.objects.create(author=users[author], body=body)
            Post.objects.filter(pk=post.pk).update(created_at=now - timedelta(hours=hours_ago))
            posts.append(post)
        return posts

    def _create_comments(self, posts, users):
        created_by_body = {}
        for post_index, author, body, parent_body in COMMENTS:
            parent = created_by_body.get(parent_body) if parent_body else None
            comment = Comment.objects.create(
                author=users[author], post=posts[post_index], body=body, parent=parent
            )
            created_by_body[body] = comment

    def _create_votes(self, posts, users):
        voters = list(users.values())
        for i, post in enumerate(posts):
            for j, voter in enumerate(voters):
                if voter == post.author:
                    continue
                # A simple deterministic spread so scores vary post to post
                # rather than every post getting an identical vote count.
                if (i + j) % 3 != 0:
                    PostVote.objects.create(user=voter, post=post, value=PostVote.UP)
                elif (i + j) % 5 == 0:
                    PostVote.objects.create(user=voter, post=post, value=PostVote.DOWN)
        for comment in Comment.objects.all():
            for voter in voters:
                if voter != comment.author:
                    CommentVote.objects.create(user=voter, comment=comment, value=CommentVote.UP)
                    break

    def _create_follows(self, users):
        for follower, followed in FOLLOWS:
            Follow.objects.get_or_create(follower=users[follower], followed=users[followed])

    def _create_game_history(self, users):
        matt, alice, bob, carol, dave = (users["matt"], users["alice"], users["bob"], users["carol"], users["dave"])

        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=matt, player2=alice, status=Match.Status.FINISHED,
            state=tic_tac_toe.initial_state(), winner=matt,
        )
        Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=bob, player2=carol, status=Match.Status.FINISHED,
            state=connect_four.initial_state(), winner=carol,
        )
        Match.objects.create(
            game=Match.Game.CHECKERS, player1=dave, player2=matt, status=Match.Status.FINISHED,
            state=checkers.initial_state(), winner=None,
        )
        Match.objects.create(
            game=Match.Game.OTHELLO, player1=alice, player2=bob, status=Match.Status.FINISHED,
            state=othello.initial_state(), winner=alice,
        )
        # One still-active match, so the "your turn"/games hub views have
        # something to show too, not just finished history.
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=carol, player2=dave, status=Match.Status.ACTIVE,
            state=tic_tac_toe.initial_state(), turn=carol,
        )

        SinglePlayerResult.objects.create(player=matt, game=SinglePlayerResult.Game.GAME_2048, score=2048)
        SinglePlayerResult.objects.create(player=alice, game=SinglePlayerResult.Game.GAME_2048, score=4096)
        SinglePlayerResult.objects.create(player=bob, game=SinglePlayerResult.Game.SNAKE, score=87)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.DOODLE_JUMP, score=1530)
        SinglePlayerResult.objects.create(player=dave, game=SinglePlayerResult.Game.WORDLE, won=True, score=4)
        SinglePlayerResult.objects.create(player=matt, game=SinglePlayerResult.Game.HANGMAN, won=True, score=1)
