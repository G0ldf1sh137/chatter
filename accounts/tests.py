import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from posts.models import Comment, CommentVote, Post, PostVote

from .models import Follow, Profile

# Smallest valid GIF, used to exercise ImageField validation without a real file.
TINY_GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class RegistrationTests(TestCase):
    def test_valid_signup_creates_user_and_profile(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "correct-horse-battery-staple",
                "password2": "correct-horse-battery-staple",
            },
        )
        self.assertRedirects(response, reverse("feed"))
        user = User.objects.get(username="bob")
        self.assertEqual(user.email, "bob@example.com")
        self.assertTrue(Profile.objects.filter(user=user).exists())

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
        self.assertRedirects(response, reverse("feed"))
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
        self.assertRedirects(response, reverse("feed"))
        user = User.objects.get(username="bob")
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")

    def test_signup_logs_the_user_in(self):
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
        self.assertTrue(response.wsgi_request.user.is_authenticated)

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

        response = self.client.post(reverse("profile-edit"), {"bio": "Hello!", "avatar": avatar})

        self.assertRedirects(response, reverse("profile", args=["dave"]))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.bio, "Hello!")
        self.assertTrue(profile.avatar)

    @override_settings(MAX_AVATAR_UPLOAD_SIZE=10)
    def test_oversized_avatar_rejected(self):
        self.client.force_login(self.user)
        avatar = SimpleUploadedFile("avatar.gif", TINY_GIF, content_type="image/gif")

        response = self.client.post(reverse("profile-edit"), {"bio": "", "avatar": avatar})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Profile.objects.get(user=self.user).avatar)
        self.assertFormError(response.context["form"], "avatar", "Image must be smaller than 0MB.")


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
