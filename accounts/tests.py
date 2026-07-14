import shutil
import tempfile
from datetime import datetime
from datetime import timezone as dt_timezone

from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import User
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from games.models import Match, SinglePlayerResult
from posts.models import Comment, CommentVote, Conversation, Post, PostVote, Repost

from .adapter import SocialAccountAdapter
from .models import Block, Follow, Mute, Profile, is_blocked_either_way, is_muted_or_blocked
from .signals import mark_social_signup_verified
from .templatetags.user_extras import at_username
from .tokens import generate_verification_token

# Smallest valid GIF, used to exercise ImageField validation without a real file.
TINY_GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class RegistrationTests(TestCase):
    def test_valid_signup_creates_unverified_user_and_profile(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertRedirects(response, reverse("verification-sent"))
        user = User.objects.get(username="bob")
        self.assertEqual(user.email, "bob@example.com")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertFalse(user.profile.email_verified)

    def test_signup_accepts_optional_first_and_last_name(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "first_name": "Bob",
                "last_name": "Smith",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertRedirects(response, reverse("verification-sent"))
        user = User.objects.get(username="bob")
        self.assertEqual(user.first_name, "Bob")
        self.assertEqual(user.last_name, "Smith")

    def test_signup_without_first_and_last_name_still_works(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertRedirects(response, reverse("verification-sent"))
        user = User.objects.get(username="bob")
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")

    def test_signup_does_not_log_the_user_in(self):
        self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        response = self.client.get(reverse("feed"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_signup_sends_verification_email(self):
        self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@example.com"])
        self.assertIn("verify-email", mail.outbox[0].body)

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="bob", password="correct-horse-battery-staple")
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="bob").count(), 1)
        self.assertFormError(response.context["form"], "username", "A user with that username already exists.")

    def test_username_with_at_sign_rejected(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob@example",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="bob@example").exists())
        self.assertFormError(response.context["form"], "username", "Usernames can't contain the '@' symbol.")

    def test_username_help_text_does_not_mention_at_sign(self):
        response = self.client.get(reverse("register"))
        self.assertContains(response, "Letters, digits and ./+/-/_ only.")
        self.assertNotContains(response, "@/./+/-/_ only.")

    def test_email_is_required(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="bob").exists())
        self.assertFormError(response.context["form"], "email", "This field is required.")


class EmailVerificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", email="bob@example.com", password="correct-horse-battery-staple")
        # create_user doesn't go through RegisterView, so the post_save signal
        # already made a Profile, but leave it explicitly unverified like a
        # fresh registration would.
        self.user.profile.email_verified = False
        self.user.profile.save(update_fields=["email_verified"])

    def test_valid_token_verifies_and_logs_in(self):
        token = generate_verification_token(self.user)
        response = self.client.get(reverse("verify-email", args=[token]))
        self.assertRedirects(response, reverse("feed"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.email_verified)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_token_shows_failure_page(self):
        response = self.client.get(reverse("verify-email", args=["not-a-real-token"]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/verification_failed.html")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.email_verified)

    def test_expired_token_shows_failure_page(self):
        token = generate_verification_token(self.user)
        # max_age=-1 forces signing.SignatureExpired regardless of real elapsed time.
        with override_settings(EMAIL_VERIFICATION_MAX_AGE=-1):
            response = self.client.get(reverse("verify-email", args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/verification_failed.html")
        self.assertContains(response, "expired")

    def test_unverified_user_cannot_log_in(self):
        response = self.client.post(
            reverse("login"), {"username": "bob", "password": "correct-horse-battery-staple"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertFormError(response.context["form"], None, [
            "Please verify your email before logging in. Check your inbox, or request a new verification link."
        ])

    def test_verified_user_can_log_in(self):
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])
        response = self.client.post(
            reverse("login"), {"username": "bob", "password": "correct-horse-battery-staple"}
        )
        self.assertRedirects(response, reverse("feed"))

    def test_resend_sends_email_for_unverified_account(self):
        self.client.post(reverse("resend-verification"), {"email": "bob@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@example.com"])

    def test_resend_is_silent_for_unknown_email(self):
        response = self.client.post(reverse("resend-verification"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("verification-sent"))
        self.assertEqual(len(mail.outbox), 0)

    def test_social_signup_is_auto_verified(self):
        mark_social_signup_verified(request=None, user=self.user, sociallogin=object())
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.email_verified)

    def test_regular_signal_call_without_sociallogin_is_ignored(self):
        mark_social_signup_verified(request=None, user=self.user)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.email_verified)


class SocialAccountLinkingTests(TestCase):
    def make_request(self):
        request = RequestFactory().get("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        MessageMiddleware(lambda r: None).process_request(request)
        return request

    def test_matching_email_connects_to_existing_account(self):
        existing = User.objects.create_user(username="matt", email="matt@example.com", password="x")
        existing.profile.email_verified = False
        existing.profile.save(update_fields=["email_verified"])

        new_user = User(username="someoauthname", email="matt@example.com")
        sociallogin = SocialLogin(user=new_user, account=SocialAccount(provider="google", uid="uid-123"))

        SocialAccountAdapter().pre_social_login(self.make_request(), sociallogin)

        self.assertEqual(sociallogin.user, existing)
        self.assertTrue(sociallogin.is_existing)
        existing.profile.refresh_from_db()
        self.assertTrue(existing.profile.email_verified)

    def test_no_matching_email_leaves_signup_as_new(self):
        new_user = User(username="brandnew", email="brandnew@example.com")
        sociallogin = SocialLogin(user=new_user, account=SocialAccount(provider="google", uid="uid-456"))

        SocialAccountAdapter().pre_social_login(self.make_request(), sociallogin)

        self.assertEqual(sociallogin.user, new_user)
        self.assertFalse(sociallogin.is_existing)

    def test_already_linked_login_is_left_alone(self):
        existing = User.objects.create_user(username="matt", email="matt@example.com", password="x")
        account = SocialAccount.objects.create(user=existing, provider="google", uid="uid-789")
        sociallogin = SocialLogin(user=existing, account=account)

        # Should not raise or try to reconnect an already-existing link.
        SocialAccountAdapter().pre_social_login(self.make_request(), sociallogin)

        self.assertEqual(sociallogin.user, existing)


class ProfileViewTests(TestCase):
    def test_profile_shows_bio_and_posts(self):
        user = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        Profile.objects.filter(user=user).update(bio="Hello, I'm Carol.")
        response = self.client.get(reverse("profile", args=["carol"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hello, I&#x27;m Carol.")

    def test_profile_shows_comments_and_counts(self):
        user = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        post = Post.objects.create(author=user, body="A post")
        Comment.objects.create(author=user, post=post, body="A comment by carol")

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertContains(response, "A comment by carol")
        self.assertContains(response, "1 post")
        self.assertContains(response, "1 comment")

    def test_profile_shows_karma_from_posts_and_comments(self):
        carol = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        voter1 = User.objects.create_user(username="voter1", password="correct-horse-battery-staple")
        voter2 = User.objects.create_user(username="voter2", password="correct-horse-battery-staple")
        post = Post.objects.create(author=carol, body="A post")
        comment = Comment.objects.create(author=carol, post=post, body="A comment")

        PostVote.objects.create(user=voter1, post=post, value=PostVote.UP)
        PostVote.objects.create(user=voter2, post=post, value=PostVote.UP)
        CommentVote.objects.create(user=voter1, comment=comment, value=CommentVote.DOWN)

        response = self.client.get(reverse("profile", args=["carol"]))

        # post: +1 self-upvote, +1 voter1, +1 voter2 = 3. comment: +1 self-upvote, -1 voter1 = 0.
        self.assertContains(response, "3 karma")
        self.assertEqual(response.context["karma"], 3)


class ProfileRepostsTests(TestCase):
    def setUp(self):
        self.carol = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        self.dave = User.objects.create_user(username="dave", password="correct-horse-battery-staple")
        self.post1 = Post.objects.create(author=self.dave, body="first")
        self.post2 = Post.objects.create(author=self.dave, body="second")

    def test_profile_lists_reposted_posts_most_recent_first(self):
        Repost.objects.create(user=self.carol, post=self.post1)
        Repost.objects.create(user=self.carol, post=self.post2)

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertEqual(list(response.context["reposts"]), [self.post2, self.post1])
        self.assertEqual(response.context["repost_count"], 2)
        self.assertContains(response, "2 reposts")

    def test_deleted_original_drops_out_of_the_list(self):
        Repost.objects.create(user=self.carol, post=self.post1)
        self.post1.deleted = True
        self.post1.body = ""
        self.post1.save(update_fields=["deleted", "body"])

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertNotIn(self.post1, list(response.context["reposts"]))

    def test_reposts_are_not_cross_contaminated_between_users(self):
        Repost.objects.create(user=self.carol, post=self.post1)
        Repost.objects.create(user=self.dave, post=self.post2)

        carol_response = self.client.get(reverse("profile", args=["carol"]))
        dave_response = self.client.get(reverse("profile", args=["dave"]))

        self.assertEqual(list(carol_response.context["reposts"]), [self.post1])
        self.assertEqual(list(dave_response.context["reposts"]), [self.post2])

    def test_profile_with_no_reposts_shows_empty_state(self):
        response = self.client.get(reverse("profile", args=["carol"]))
        self.assertContains(response, "No reposts yet.")
        self.assertEqual(response.context["repost_count"], 0)


class RepostCommentRenderingTests(TestCase):
    def setUp(self):
        self.carol = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        self.dave = User.objects.create_user(username="dave", password="correct-horse-battery-staple")
        self.post = Post.objects.create(author=self.dave, body="an original post")

    def test_repost_with_comment_shows_it_above_a_nested_original(self):
        Repost.objects.create(user=self.carol, post=self.post, comment="my take on this")

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertContains(response, "my take on this")
        self.assertContains(response, "an original post")

    def test_plain_repost_renders_without_the_comment_wrapper(self):
        Repost.objects.create(user=self.carol, post=self.post)

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertEqual(response.context["reposts"][0].repost_comment, "")


class AtUsernameFilterTests(TestCase):
    def test_prefixes_a_username_with_at_sign(self):
        self.assertEqual(at_username("carol"), "@carol")

    def test_empty_value_passes_through_unchanged(self):
        self.assertEqual(at_username(""), "")


class UsernameDisplayTests(TestCase):
    def test_profile_heading_shows_at_prefixed_username(self):
        User.objects.create_user(username="carol", password="correct-horse-battery-staple")

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertContains(response, "@carol")
        self.assertNotContains(response, ">carol<")

    def test_feed_post_card_shows_at_prefixed_author(self):
        author = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        Post.objects.create(author=author, body="Hello from carol")

        response = self.client.get(reverse("feed"))

        self.assertContains(response, "@carol")

    def test_header_nav_shows_at_prefixed_logged_in_username(self):
        user = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        self.client.force_login(user)

        response = self.client.get(reverse("feed"))

        self.assertContains(response, "@carol")


class ProfileGamesIntegrationTests(TestCase):
    def test_profile_shows_accurate_game_stats(self):
        carol = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        dave = User.objects.create_user(username="dave", password="correct-horse-battery-staple")

        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=carol, player2=dave,
            status=Match.Status.FINISHED, winner=carol,
        )
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=dave, player2=carol,
            status=Match.Status.FINISHED, winner=dave,
        )
        Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=carol, player2=dave,
            status=Match.Status.FINISHED, winner=None,
        )
        Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=carol, player2=dave,
            status=Match.Status.FINISHED, winner=carol,
        )
        Match.objects.create(
            game=Match.Game.CHECKERS, player1=dave, player2=carol,
            status=Match.Status.FINISHED, winner=dave,
        )
        Match.objects.create(
            game=Match.Game.OTHELLO, player1=carol, player2=dave,
            status=Match.Status.FINISHED, winner=None,
        )
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.HANGMAN, won=True)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.HANGMAN, won=False)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.GAME_2048, score=750)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.GAME_2048, score=300)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.SNAKE, score=12)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.DOODLE_JUMP, score=560)
        SinglePlayerResult.objects.create(player=carol, game=SinglePlayerResult.Game.WORDLE, score=5)

        response = self.client.get(reverse("profile", args=["carol"]))

        self.assertEqual(response.context["ttt_record"], {"wins": 1, "losses": 1, "draws": 0})
        self.assertEqual(response.context["rps_record"], {"wins": 0, "losses": 0, "draws": 1})
        self.assertEqual(response.context["connect4_record"], {"wins": 1, "losses": 0, "draws": 0})
        self.assertEqual(response.context["checkers_record"], {"wins": 0, "losses": 1, "draws": 0})
        self.assertEqual(response.context["othello_record"], {"wins": 0, "losses": 0, "draws": 1})
        self.assertEqual(response.context["hangman_wins"], 1)
        self.assertEqual(response.context["high_score_2048"], 750)
        self.assertEqual(response.context["snake_high_score"], 12)
        self.assertEqual(response.context["doodle_high_score"], 560)
        self.assertEqual(response.context["wordle_high_score"], 5)
        self.assertContains(response, "750")
        self.assertContains(response, "560")


class ProfileEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dave", password="correct-horse-battery-staple")
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

    def test_anonymous_cannot_edit_profile(self):
        response = self.client.post(reverse("profile-edit"), {"bio": "hacked"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Profile.objects.get(user=self.user).bio, "")

    def test_user_can_update_bio_and_avatar(self):
        self.client.force_login(self.user)
        avatar = SimpleUploadedFile("avatar.gif", TINY_GIF, content_type="image/gif")

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "dave",
                "bio": "Hello!",
                "avatar": avatar,
                "timezone": "UTC",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertRedirects(response, reverse("profile", args=["dave"]))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.bio, "Hello!")
        self.assertTrue(profile.avatar)

    @override_settings(MAX_AVATAR_UPLOAD_SIZE=10)
    def test_oversized_avatar_rejected(self):
        self.client.force_login(self.user)
        avatar = SimpleUploadedFile("avatar.gif", TINY_GIF, content_type="image/gif")

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "dave",
                "bio": "",
                "avatar": avatar,
                "timezone": "UTC",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Profile.objects.get(user=self.user).avatar)
        self.assertFormError(response.context["form"], "avatar", "Image must be smaller than 0MB.")

    def test_user_can_update_username_and_names(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "davethegreat",
                "first_name": "Dave",
                "last_name": "Grohl",
                "bio": "",
                "timezone": "UTC",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertRedirects(response, reverse("profile", args=["davethegreat"]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "davethegreat")
        self.assertEqual(self.user.first_name, "Dave")
        self.assertEqual(self.user.last_name, "Grohl")

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="erin", password="correct-horse-battery-staple")
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "erin",
                "bio": "",
                "timezone": "UTC",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["user_form"], "username", "A user with that username already exists."
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "dave")
        # The rejected, unsaved "erin" shouldn't leak onto request.user - the
        # header's nav link reads from it and would otherwise point at erin's
        # profile instead of dave's for this response.
        self.assertEqual(response.context["user"].username, "dave")
        self.assertContains(response, reverse("profile", args=["dave"]))
        self.assertNotContains(response, reverse("profile", args=["erin"]))

    def test_blank_username_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "",
                "bio": "",
                "timezone": "UTC",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["user_form"], "username", "This field is required.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "dave")

    def test_username_with_at_sign_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "dave@example",
                "bio": "",
                "timezone": "UTC",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["user_form"], "username", "Usernames can't contain the '@' symbol."
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "dave")

    def test_username_help_text_does_not_mention_at_sign(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("profile-edit"))

        self.assertContains(response, "Letters, digits and ./+/-/_ only.")
        self.assertNotContains(response, "@/./+/-/_ only.")


class UserTimezoneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dave", password="correct-horse-battery-staple")

    def test_profile_edit_saves_timezone(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "dave",
                "bio": "",
                "timezone": "America/New_York",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertRedirects(response, reverse("profile", args=["dave"]))
        self.assertEqual(Profile.objects.get(user=self.user).timezone, "America/New_York")

    def test_invalid_timezone_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile-edit"),
            {
                "username": "dave",
                "bio": "",
                "timezone": "Not/A_Zone",
                "notify_on_mentions": "on",
                "notify_on_replies": "on",
                "notify_on_upvotes": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Profile.objects.get(user=self.user).timezone, "UTC")

    def test_datetimes_render_in_the_viewers_timezone(self):
        author = User.objects.create_user(username="erin", password="correct-horse-battery-staple")
        post = Post.objects.create(author=author, body="Hello")
        # auto_now_add ignores an explicit value passed to create(), so set
        # a known UTC instant directly via update() instead.
        utc_instant = datetime(2026, 1, 1, 12, 0, tzinfo=dt_timezone.utc)
        Post.objects.filter(pk=post.pk).update(created_at=utc_instant)

        profile = Profile.objects.get(user=self.user)
        profile.timezone = "America/New_York"
        profile.save(update_fields=["timezone"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("post-detail", args=[post.pk]))

        # Noon UTC on Jan 1 is 7 a.m. in New York (UTC-5 in January).
        self.assertContains(response, "7 a.m.")
        self.assertNotContains(response, "noon")

    def test_anonymous_viewer_sees_utc(self):
        author = User.objects.create_user(username="erin", password="correct-horse-battery-staple")
        post = Post.objects.create(author=author, body="Hello")
        utc_instant = datetime(2026, 1, 1, 12, 0, tzinfo=dt_timezone.utc)
        Post.objects.filter(pk=post.pk).update(created_at=utc_instant)

        response = self.client.get(reverse("post-detail", args=[post.pk]))

        self.assertContains(response, "noon")


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dave", password="correct-horse-battery-staple")

    def test_anonymous_cannot_access(self):
        response = self.client.post(
            reverse("password-change"),
            {"old_password": "x", "new_password1": "y", "new_password2": "y"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_user_can_change_password_with_correct_old_password(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password-change"),
            {
                "old_password": "correct-horse-battery-staple",
                "new_password1": "new-correct-horse-staple",
                "new_password2": "new-correct-horse-staple",
            },
        )

        self.assertRedirects(response, reverse("profile-edit"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-correct-horse-staple"))

    def test_session_stays_authenticated_after_change(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse("password-change"),
            {
                "old_password": "correct-horse-battery-staple",
                "new_password1": "new-correct-horse-staple",
                "new_password2": "new-correct-horse-staple",
            },
        )

        response = self.client.get(reverse("profile-edit"))
        self.assertEqual(response.status_code, 200)

    def test_wrong_old_password_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password-change"),
            {
                "old_password": "wrong-password",
                "new_password1": "new-correct-horse-staple",
                "new_password2": "new-correct-horse-staple",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("correct-horse-battery-staple"))

    def test_mismatched_new_passwords_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password-change"),
            {
                "old_password": "correct-horse-battery-staple",
                "new_password1": "new-correct-horse-staple",
                "new_password2": "something-else-entirely",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("correct-horse-battery-staple"))

    def test_social_only_user_can_set_password_without_old_password(self):
        social_user = User.objects.create_user(username="erin", password=None)
        self.assertFalse(social_user.has_usable_password())
        self.client.force_login(social_user)

        response = self.client.post(
            reverse("password-change"),
            {"new_password1": "brand-new-password-123", "new_password2": "brand-new-password-123"},
        )

        self.assertRedirects(response, reverse("profile-edit"))
        social_user.refresh_from_db()
        self.assertTrue(social_user.check_password("brand-new-password-123"))


class UserSearchViewTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(username="dave", password="correct-horse-battery-staple")
        User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        User.objects.create_user(username="caroline", password="correct-horse-battery-staple")
        User.objects.create_user(username="bob", password="correct-horse-battery-staple")

    def test_anonymous_user_cannot_search(self):
        response = self.client.get(reverse("user-search"), {"q": "car"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_prefix_match_is_case_insensitive(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("user-search"), {"q": "CAR"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"usernames": ["carol", "caroline"]})

    def test_non_matching_query_returns_empty_list(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("user-search"), {"q": "zzz"})

        self.assertEqual(response.json(), {"usernames": []})

    def test_blank_query_returns_empty_list_without_matching_everyone(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("user-search"), {"q": ""})

        self.assertEqual(response.json(), {"usernames": []})

    def test_results_are_capped(self):
        self.client.force_login(self.viewer)
        for i in range(10):
            User.objects.create_user(username=f"carfan{i}", password="correct-horse-battery-staple")

        response = self.client.get(reverse("user-search"), {"q": "car"})

        self.assertEqual(len(response.json()["usernames"]), 8)


class SiteFooterTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="correct-horse-battery-staple"
        )
        self.dave = User.objects.create_user(username="dave", password="correct-horse-battery-staple")

    def test_copyright_shows_current_year(self):
        current_year = str(datetime.now().year)

        response = self.client.get(reverse("feed"))

        self.assertContains(response, f"&copy; {current_year} Chatter.")

    def test_anonymous_visitor_does_not_see_message_link(self):
        response = self.client.get(reverse("feed"))
        self.assertNotContains(response, "Send us a message")

    def test_logged_in_user_sees_message_link_to_admin(self):
        self.client.force_login(self.dave)

        response = self.client.get(reverse("feed"))

        self.assertContains(response, "Send us a message")
        self.assertContains(response, reverse("conversation-start", args=["admin"]))

    def test_admin_does_not_see_a_self_message_link(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("feed"))

        self.assertNotContains(response, "Send us a message")

    def test_message_link_starts_a_conversation_with_the_admin(self):
        self.client.force_login(self.dave)

        response = self.client.post(reverse("conversation-start", args=["admin"]))

        conversation = Conversation.objects.get()
        self.assertRedirects(response, reverse("conversation-detail", args=[conversation.pk]))
        self.assertIn(self.dave, [conversation.user1, conversation.user2])
        self.assertIn(self.admin, [conversation.user1, conversation.user2])


class FollowTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.bob = User.objects.create_user(username="bob", password="correct-horse-battery-staple")

    def test_anonymous_cannot_follow(self):
        response = self.client.post(reverse("follow", args=["bob"]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Follow.objects.filter(follower=self.alice, followed=self.bob).exists())

    def test_follow_and_unfollow(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("follow", args=["bob"]))
        self.assertTrue(Follow.objects.filter(follower=self.alice, followed=self.bob).exists())

        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertContains(response, "1 follower")

        self.client.post(reverse("unfollow", args=["bob"]))
        self.assertFalse(Follow.objects.filter(follower=self.alice, followed=self.bob).exists())

    def test_follow_is_idempotent(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("follow", args=["bob"]))
        self.client.post(reverse("follow", args=["bob"]))
        self.assertEqual(Follow.objects.filter(follower=self.alice, followed=self.bob).count(), 1)

    def test_cannot_follow_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("follow", args=["alice"]))
        self.assertFalse(Follow.objects.filter(follower=self.alice, followed=self.alice).exists())


class UserListViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.bob = User.objects.create_user(username="bob", password="correct-horse-battery-staple")
        self.carol = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        Follow.objects.create(follower=self.bob, followed=self.alice)
        Follow.objects.create(follower=self.carol, followed=self.alice)
        Follow.objects.create(follower=self.alice, followed=self.bob)

    def test_followers_list_shows_only_those_following_the_profile_user(self):
        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertEqual(set(response.context["users"]), {self.bob, self.carol})

    def test_following_list_shows_only_those_the_profile_user_follows(self):
        response = self.client.get(reverse("following-list", args=["alice"]))
        self.assertEqual(set(response.context["users"]), {self.bob})

    def test_authenticated_viewer_sees_follow_button_for_someone_not_yet_followed(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertContains(response, reverse("follow", args=["carol"]))
        self.assertNotContains(response, reverse("unfollow", args=["carol"]))

    def test_authenticated_viewer_sees_unfollow_button_for_someone_already_followed(self):
        self.client.force_login(self.carol)
        Follow.objects.create(follower=self.carol, followed=self.bob)
        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertContains(response, reverse("unfollow", args=["bob"]))

    def test_no_follow_button_for_own_row(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertNotContains(response, reverse("follow", args=["bob"]))
        self.assertNotContains(response, reverse("unfollow", args=["bob"]))

    def test_anonymous_visitor_sees_the_list_with_no_follow_buttons(self):
        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("follow", args=["bob"]))

    def test_muted_or_blocked_user_still_appears_in_the_list(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        Block.objects.create(blocker=self.alice, blocked=self.carol)
        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertEqual(set(response.context["users"]), {self.bob, self.carol})

    def test_pagination_spans_a_second_page(self):
        for i in range(25):
            follower = User.objects.create_user(username=f"follower{i}", password="correct-horse-battery-staple")
            Follow.objects.create(follower=follower, followed=self.alice)

        response = self.client.get(reverse("followers-list", args=["alice"]))
        self.assertTrue(response.context["page_obj"].has_next())


class MuteTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.bob = User.objects.create_user(username="bob", password="correct-horse-battery-staple")

    def test_anonymous_cannot_mute(self):
        response = self.client.post(reverse("mute", args=["bob"]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Mute.objects.filter(muter=self.alice, muted=self.bob).exists())

    def test_mute_and_unmute(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("mute", args=["bob"]))
        self.assertTrue(Mute.objects.filter(muter=self.alice, muted=self.bob).exists())

        self.client.post(reverse("unmute", args=["bob"]))
        self.assertFalse(Mute.objects.filter(muter=self.alice, muted=self.bob).exists())

    def test_mute_is_idempotent(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("mute", args=["bob"]))
        self.client.post(reverse("mute", args=["bob"]))
        self.assertEqual(Mute.objects.filter(muter=self.alice, muted=self.bob).count(), 1)

    def test_cannot_mute_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("mute", args=["alice"]))
        self.assertFalse(Mute.objects.filter(muter=self.alice, muted=self.alice).exists())

    def test_is_muted_or_blocked_true_for_a_mute(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.assertTrue(is_muted_or_blocked(self.alice, self.bob))
        self.assertFalse(is_muted_or_blocked(self.bob, self.alice))


class BlockTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.bob = User.objects.create_user(username="bob", password="correct-horse-battery-staple")

    def test_anonymous_cannot_block(self):
        response = self.client.post(reverse("block", args=["bob"]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Block.objects.filter(blocker=self.alice, blocked=self.bob).exists())

    def test_block_and_unblock(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("block", args=["bob"]))
        self.assertTrue(Block.objects.filter(blocker=self.alice, blocked=self.bob).exists())

        self.client.post(reverse("unblock", args=["bob"]))
        self.assertFalse(Block.objects.filter(blocker=self.alice, blocked=self.bob).exists())

    def test_block_is_idempotent(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("block", args=["bob"]))
        self.client.post(reverse("block", args=["bob"]))
        self.assertEqual(Block.objects.filter(blocker=self.alice, blocked=self.bob).count(), 1)

    def test_cannot_block_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("block", args=["alice"]))
        self.assertFalse(Block.objects.filter(blocker=self.alice, blocked=self.alice).exists())

    def test_is_muted_or_blocked_true_for_a_block(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.assertTrue(is_muted_or_blocked(self.alice, self.bob))

    def test_is_blocked_either_way_regardless_of_direction(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.assertTrue(is_blocked_either_way(self.alice, self.bob))
        self.assertTrue(is_blocked_either_way(self.bob, self.alice))

    def test_is_blocked_either_way_false_with_no_block(self):
        self.assertFalse(is_blocked_either_way(self.alice, self.bob))


class MuteBlockProfilePageTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.bob = User.objects.create_user(username="bob", password="correct-horse-battery-staple")

    def test_shows_mute_and_block_buttons_by_default(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertContains(response, "Mute")
        self.assertContains(response, "Block")
        self.assertContains(response, reverse("conversation-start", args=["bob"]))

    def test_shows_unmute_when_already_muted(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertContains(response, "Unmute")

    def test_shows_unblock_when_already_blocked(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertContains(response, "Unblock")

    def test_hides_message_and_challenge_buttons_when_blocked(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertNotContains(response, reverse("conversation-start", args=["bob"]))
        self.assertNotContains(response, "Challenge to Tic-Tac-Toe")

    def test_hides_message_button_when_blocked_by_the_other_user(self):
        Block.objects.create(blocker=self.bob, blocked=self.alice)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertNotContains(response, reverse("conversation-start", args=["bob"]))

    def test_mute_does_not_hide_message_button(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("profile", args=["bob"]))
        self.assertContains(response, reverse("conversation-start", args=["bob"]))
