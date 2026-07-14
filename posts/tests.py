import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Block, Follow, Mute

from .hashtags import extract_hashtag_names
from .markdown import render_markdown
from .mentions import extract_mentioned_users
from .models import (
    Comment,
    CommentVote,
    Conversation,
    Message,
    Notification,
    Post,
    PostReaction,
    PostVote,
    Report,
    SavedPost,
    Tag,
)
from .templatetags.post_extras import group_reactions
from .views import (
    build_comment_tree,
    get_or_create_conversation,
    toggle_reaction,
    toggle_vote,
    unread_message_count,
    unread_notification_count,
)

# Smallest valid GIF, used to exercise ImageField validation without a real file.
TINY_GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def make_user(username):
    return User.objects.create_user(username=username, password="correct-horse-battery-staple")


class AuthGatingTests(TestCase):
    def test_anonymous_cannot_view_post_create_page(self):
        response = self.client.get(reverse("post-create"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('post-create')}")

    def test_anonymous_cannot_create_post(self):
        response = self.client.post(reverse("post-create"), {"body": "hello"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 0)

    def test_anonymous_cannot_comment(self):
        author = make_user("alice")
        post = Post.objects.create(author=author, body="hello")
        response = self.client.post(reverse("comment-create", args=[post.pk]), {"body": "hi"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comment.objects.count(), 0)


class PostTests(TestCase):
    def test_authenticated_user_can_create_post(self):
        user = make_user("alice")
        self.client.force_login(user)
        response = self.client.post(reverse("post-create"), {"body": "hello world"})
        post = Post.objects.get()
        self.assertRedirects(response, reverse("post-detail", args=[post.pk]))
        self.assertEqual(post.author, user)
        self.assertEqual(post.body, "hello world")

    def test_first_line_returns_only_first_line(self):
        post = Post.objects.create(author=make_user("alice"), body="line one\nline two\nline three")
        self.assertEqual(post.first_line(), "line one")

    def test_feed_shows_only_first_line_linked_to_post_detail(self):
        user = make_user("alice")
        post = Post.objects.create(author=user, body="first line\nsecond line")
        response = self.client.get(reverse("feed"))
        self.assertContains(response, "first line")
        self.assertNotContains(response, "second line")
        self.assertContains(response, reverse("post-detail", args=[post.pk]))

    def test_feed_links_single_line_post_to_detail(self):
        user = make_user("alice")
        post = Post.objects.create(author=user, body="just one line")
        response = self.client.get(reverse("feed"))
        self.assertContains(response, reverse("post-detail", args=[post.pk]))

    def test_feed_orders_tied_posts_newest_first(self):
        user = make_user("alice")
        first = Post.objects.create(author=user, body="first")
        second = Post.objects.create(author=user, body="second")
        response = self.client.get(reverse("feed"))
        self.assertEqual(list(response.context["posts"]), [second, first])

    def test_feed_orders_posts_by_score_first(self):
        author = make_user("alice")
        voter1 = make_user("bob")
        voter2 = make_user("carol")
        low_score = Post.objects.create(author=author, body="low score")
        high_score = Post.objects.create(author=author, body="high score")
        PostVote.objects.create(user=voter1, post=high_score, value=PostVote.UP)
        PostVote.objects.create(user=voter2, post=high_score, value=PostVote.UP)

        response = self.client.get(reverse("feed"))

        # high_score created after low_score but outranks it: 3 upvotes vs 1.
        self.assertEqual(list(response.context["posts"]), [high_score, low_score])

    def test_feed_ranks_more_comment_karma_higher(self):
        author = make_user("dave")
        commenter = make_user("eve")
        voter1 = make_user("bob")
        voter2 = make_user("carol")

        with_comments = Post.objects.create(author=author, body="lively discussion")
        no_comments = Post.objects.create(author=author, body="quiet post")
        now = timezone.now()
        Post.objects.filter(pk__in=[with_comments.pk, no_comments.pk]).update(created_at=now)

        comment = Comment.objects.create(author=commenter, post=with_comments, body="great point")
        CommentVote.objects.create(user=voter1, comment=comment, value=CommentVote.UP)
        CommentVote.objects.create(user=voter2, comment=comment, value=CommentVote.UP)

        response = self.client.get(reverse("feed"))

        # Same author, same score, same age - only the comment thread's karma differs.
        self.assertEqual(list(response.context["posts"]), [with_comments, no_comments])

    def test_feed_ranks_higher_poster_karma_above_lower(self):
        popular_author = make_user("dave")
        new_author = make_user("erin")
        voter1 = make_user("bob")
        voter2 = make_user("carol")
        voter3 = make_user("frank")

        older_popular_post = Post.objects.create(author=popular_author, body="past hit")
        for voter in (voter1, voter2, voter3):
            PostVote.objects.create(user=voter, post=older_popular_post, value=PostVote.UP)

        from_popular_author = Post.objects.create(author=popular_author, body="new from a popular author")
        from_new_author = Post.objects.create(author=new_author, body="new from a fresh author")
        now = timezone.now()
        Post.objects.filter(pk__in=[from_popular_author.pk, from_new_author.pk]).update(created_at=now)

        response = self.client.get(reverse("feed"))
        posts = list(response.context["posts"])

        # Same score, same age - only the authors' overall karma differs.
        self.assertLess(posts.index(from_popular_author), posts.index(from_new_author))

    def test_feed_decay_favors_recent_post_over_old_high_karma_post(self):
        author = make_user("dave")
        voter1 = make_user("bob")
        voter2 = make_user("carol")
        voter3 = make_user("frank")

        old_high_karma = Post.objects.create(author=author, body="old but popular")
        for voter in (voter1, voter2, voter3):
            PostVote.objects.create(user=voter, post=old_high_karma, value=PostVote.UP)
        Post.objects.filter(pk=old_high_karma.pk).update(created_at=timezone.now() - timedelta(days=30))
        old_high_karma.refresh_from_db()

        new_modest = Post.objects.create(author=make_user("erin"), body="brand new")

        response = self.client.get(reverse("feed"))

        # A month-old post with 4 upvotes has decayed enough that a brand-new post
        # with just its author's self-upvote now outranks it.
        self.assertEqual(list(response.context["posts"]), [new_modest, old_high_karma])

    def test_feed_sort_top_ignores_decay_and_orders_by_score(self):
        author = make_user("dave")
        voter1 = make_user("bob")
        voter2 = make_user("carol")
        voter3 = make_user("frank")

        old_high_karma = Post.objects.create(author=author, body="old but popular")
        for voter in (voter1, voter2, voter3):
            PostVote.objects.create(user=voter, post=old_high_karma, value=PostVote.UP)
        Post.objects.filter(pk=old_high_karma.pk).update(created_at=timezone.now() - timedelta(days=30))
        old_high_karma.refresh_from_db()

        new_modest = Post.objects.create(author=make_user("erin"), body="brand new")

        response = self.client.get(reverse("feed"), {"sort": "top"})

        # Unlike the default ranking, "top" ignores age entirely - raw score wins.
        self.assertEqual(list(response.context["posts"]), [old_high_karma, new_modest])

    def test_feed_sort_new_orders_by_recency_regardless_of_score(self):
        author = make_user("dave")
        voter1 = make_user("bob")
        voter2 = make_user("carol")
        voter3 = make_user("frank")

        old_high_karma = Post.objects.create(author=author, body="old but popular")
        for voter in (voter1, voter2, voter3):
            PostVote.objects.create(user=voter, post=old_high_karma, value=PostVote.UP)
        Post.objects.filter(pk=old_high_karma.pk).update(created_at=timezone.now() - timedelta(days=30))
        old_high_karma.refresh_from_db()

        new_modest = Post.objects.create(author=make_user("erin"), body="brand new")

        response = self.client.get(reverse("feed"), {"sort": "new"})

        self.assertEqual(list(response.context["posts"]), [new_modest, old_high_karma])

    def test_feed_sort_defaults_to_ranked_algorithm(self):
        response = self.client.get(reverse("feed"))
        self.assertEqual(response.context["active_sort"], "default")

    def test_feed_sort_rejects_invalid_value(self):
        response = self.client.get(reverse("feed"), {"sort": "not-a-real-option"})
        self.assertEqual(response.context["active_sort"], "default")

    def test_following_feed_requires_login(self):
        response = self.client.get(reverse("following-feed"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('following-feed')}")

    def test_following_feed_shows_only_followed_authors(self):
        viewer = make_user("alice")
        followed = make_user("bob")
        stranger = make_user("mallory")
        followed_post = Post.objects.create(author=followed, body="from bob")
        Post.objects.create(author=stranger, body="from mallory")
        Follow.objects.create(follower=viewer, followed=followed)

        self.client.force_login(viewer)
        response = self.client.get(reverse("following-feed"))

        self.assertEqual(list(response.context["posts"]), [followed_post])

    def test_following_feed_empty_when_following_nobody(self):
        viewer = make_user("alice")
        make_user("bob")
        Post.objects.create(author=User.objects.get(username="bob"), body="hello")

        self.client.force_login(viewer)
        response = self.client.get(reverse("following-feed"))

        self.assertEqual(list(response.context["posts"]), [])

    def test_author_can_edit_own_post(self):
        user = make_user("alice")
        post = Post.objects.create(author=user, body="original")
        self.client.force_login(user)
        response = self.client.post(reverse("post-edit", args=[post.pk]), {"body": "edited"})
        post.refresh_from_db()
        self.assertRedirects(response, reverse("post-detail", args=[post.pk]))
        self.assertEqual(post.body, "edited")

    def test_non_author_cannot_edit_post(self):
        author = make_user("alice")
        other = make_user("mallory")
        post = Post.objects.create(author=author, body="original")
        self.client.force_login(other)
        response = self.client.post(reverse("post-edit", args=[post.pk]), {"body": "hacked"})
        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.body, "original")

    def test_editing_a_post_marks_it_edited(self):
        user = make_user("alice")
        post = Post.objects.create(author=user, body="original")
        self.client.force_login(user)
        self.client.post(reverse("post-edit", args=[post.pk]), {"body": "edited"})
        post.refresh_from_db()
        self.assertTrue(post.edited)

    def test_resubmitting_unchanged_body_does_not_mark_edited(self):
        user = make_user("alice")
        post = Post.objects.create(author=user, body="original")
        self.client.force_login(user)
        self.client.post(reverse("post-edit", args=[post.pk]), {"body": "original"})
        post.refresh_from_db()
        self.assertFalse(post.edited)


class MuteBlockFeedTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.bobs_post = Post.objects.create(author=self.bob, body="hello from bob")

    def test_muting_hides_their_posts_from_your_feed(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("feed"))

        self.assertNotIn(self.bobs_post, response.context["posts"])

    def test_blocking_hides_their_posts_from_your_feed(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("feed"))

        self.assertNotIn(self.bobs_post, response.context["posts"])

    def test_a_muted_users_posts_still_show_up_for_everyone_else(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        carol = make_user("carol")
        self.client.force_login(carol)

        response = self.client.get(reverse("feed"))

        self.assertIn(self.bobs_post, response.context["posts"])

    def test_anonymous_visitor_sees_everything(self):
        response = self.client.get(reverse("feed"))
        self.assertIn(self.bobs_post, response.context["posts"])


class PostDeleteTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.post = Post.objects.create(author=self.author, body="original")

    def test_author_can_delete_own_post(self):
        self.client.force_login(self.author)

        response = self.client.post(reverse("post-delete", args=[self.post.pk]))

        self.assertRedirects(response, reverse("post-detail", args=[self.post.pk]))
        self.post.refresh_from_db()
        self.assertTrue(self.post.deleted)
        self.assertEqual(self.post.body, "")

    def test_non_author_cannot_delete_post(self):
        other = make_user("mallory")
        self.client.force_login(other)

        response = self.client.post(reverse("post-delete", args=[self.post.pk]))

        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertFalse(self.post.deleted)
        self.assertEqual(self.post.body, "original")

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("post-delete", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.post.refresh_from_db()
        self.assertFalse(self.post.deleted)

    def test_deleted_post_shows_placeholder_instead_of_body(self):
        self.client.force_login(self.author)
        self.client.post(reverse("post-delete", args=[self.post.pk]))

        response = self.client.get(reverse("post-detail", args=[self.post.pk]))

        self.assertContains(response, "[deleted]")
        self.assertNotContains(response, "original")

    def test_deleted_post_card_shows_placeholder_on_the_feed(self):
        self.client.force_login(self.author)
        self.client.post(reverse("post-delete", args=[self.post.pk]))

        response = self.client.get(reverse("feed"))

        self.assertContains(response, "[deleted]")

    def test_cannot_edit_an_already_deleted_post(self):
        self.client.force_login(self.author)
        self.client.post(reverse("post-delete", args=[self.post.pk]))

        response = self.client.post(reverse("post-edit", args=[self.post.pk]), {"body": "resurrected"})

        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.body, "")

    def test_deleting_a_post_does_not_cascade_to_its_comments(self):
        comment = Comment.objects.create(author=self.author, post=self.post, body="a comment")
        self.client.force_login(self.author)

        self.client.post(reverse("post-delete", args=[self.post.pk]))

        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())


class SavedPostTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.bob, body="a post worth saving")

    def test_authenticated_user_can_save_a_post(self):
        self.client.force_login(self.alice)

        response = self.client.post(reverse("post-save", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SavedPost.objects.filter(user=self.alice, post=self.post).exists())

    def test_saving_twice_is_idempotent(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("post-save", args=[self.post.pk]))
        self.client.post(reverse("post-save", args=[self.post.pk]))

        self.assertEqual(SavedPost.objects.filter(user=self.alice, post=self.post).count(), 1)

    def test_user_can_unsave_a_post(self):
        SavedPost.objects.create(user=self.alice, post=self.post)
        self.client.force_login(self.alice)

        response = self.client.post(reverse("post-unsave", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SavedPost.objects.filter(user=self.alice, post=self.post).exists())

    def test_unsaving_a_post_not_saved_is_a_no_op(self):
        self.client.force_login(self.alice)

        response = self.client.post(reverse("post-unsave", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SavedPost.objects.filter(user=self.alice, post=self.post).exists())

    def test_anonymous_cannot_save(self):
        response = self.client.post(reverse("post-save", args=[self.post.pk]))
        self.assertIn(reverse("login"), response.url)

    def test_anonymous_cannot_unsave(self):
        response = self.client.post(reverse("post-unsave", args=[self.post.pk]))
        self.assertIn(reverse("login"), response.url)

    def test_saved_posts_list_shows_only_current_users_saves_most_recent_first(self):
        other_post = Post.objects.create(author=self.bob, body="another post")
        SavedPost.objects.create(user=self.alice, post=self.post)
        SavedPost.objects.create(user=self.alice, post=other_post)
        SavedPost.objects.create(user=self.bob, post=self.post)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("saved-posts"))

        self.assertEqual(list(response.context["posts"]), [other_post, self.post])

    def test_saved_posts_list_includes_a_deleted_post_with_placeholder(self):
        SavedPost.objects.create(user=self.alice, post=self.post)
        self.post.body = ""
        self.post.deleted = True
        self.post.save(update_fields=["body", "deleted"])
        self.client.force_login(self.alice)

        response = self.client.get(reverse("saved-posts"))

        self.assertContains(response, "[deleted]")

    def test_saving_a_muted_authors_post_still_shows_in_saved_list(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        SavedPost.objects.create(user=self.alice, post=self.post)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("saved-posts"))

        self.assertIn(self.post, response.context["posts"])

    def test_saving_a_blocked_authors_post_still_shows_in_saved_list(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        SavedPost.objects.create(user=self.alice, post=self.post)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("saved-posts"))

        self.assertIn(self.post, response.context["posts"])

    def test_is_saved_is_true_on_the_feed_after_saving(self):
        SavedPost.objects.create(user=self.alice, post=self.post)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("feed"))

        post = next(p for p in response.context["posts"] if p.pk == self.post.pk)
        self.assertTrue(post.is_saved)

    def test_is_saved_is_false_on_the_feed_when_not_saved(self):
        self.client.force_login(self.alice)

        response = self.client.get(reverse("feed"))

        post = next(p for p in response.context["posts"] if p.pk == self.post.pk)
        self.assertFalse(post.is_saved)

    def test_is_saved_is_false_for_anonymous_visitors(self):
        response = self.client.get(reverse("feed"))
        post = next(p for p in response.context["posts"] if p.pk == self.post.pk)
        self.assertFalse(post.is_saved)


class ReportTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")
        self.comment = Comment.objects.create(author=self.alice, post=self.post, body="a comment")

    def test_non_author_can_report_a_post(self):
        self.client.force_login(self.bob)

        response = self.client.post(reverse("post-report", args=[self.post.pk]), {"reason": "spam"})

        self.assertEqual(response.status_code, 302)
        report = Report.objects.get(reporter=self.bob, post=self.post, comment=None)
        self.assertEqual(report.status, Report.Status.OPEN)
        self.assertEqual(report.reason, "spam")

    def test_non_author_can_report_a_comment(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-report", args=[self.comment.pk]), {"reason": "rude"})

        report = Report.objects.get(reporter=self.bob, comment=self.comment)
        self.assertEqual(report.post, self.post)
        self.assertEqual(report.reason, "rude")

    def test_author_cannot_report_own_post(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("post-report", args=[self.post.pk]), {"reason": "spam"})

        self.assertFalse(Report.objects.filter(post=self.post, comment=None).exists())

    def test_author_cannot_report_own_comment(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("comment-report", args=[self.comment.pk]), {"reason": "rude"})

        self.assertFalse(Report.objects.filter(comment=self.comment).exists())

    def test_reporting_the_same_post_twice_is_idempotent(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("post-report", args=[self.post.pk]), {"reason": "spam"})
        self.client.post(reverse("post-report", args=[self.post.pk]), {"reason": "spam again"})

        self.assertEqual(Report.objects.filter(reporter=self.bob, post=self.post, comment=None).count(), 1)

    def test_empty_reason_is_accepted(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("post-report", args=[self.post.pk]))

        report = Report.objects.get(reporter=self.bob, post=self.post, comment=None)
        self.assertEqual(report.reason, "")

    def test_anonymous_cannot_report_a_post(self):
        response = self.client.post(reverse("post-report", args=[self.post.pk]), {"reason": "spam"})
        self.assertIn(reverse("login"), response.url)
        self.assertFalse(Report.objects.exists())

    def test_anonymous_cannot_report_a_comment(self):
        response = self.client.post(reverse("comment-report", args=[self.comment.pk]), {"reason": "rude"})
        self.assertIn(reverse("login"), response.url)
        self.assertFalse(Report.objects.exists())


class PostImageTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

    def test_creating_a_post_with_an_image_stores_it(self):
        self.client.force_login(self.author)
        image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")

        self.client.post(reverse("post-create"), {"body": "look at this", "image": image})

        post = Post.objects.get(body="look at this")
        self.assertTrue(post.image)
        self.assertIn("photo", post.image.name)

    def test_creating_a_post_without_an_image_still_works(self):
        self.client.force_login(self.author)

        response = self.client.post(reverse("post-create"), {"body": "no image here"})

        post = Post.objects.get(body="no image here")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(post.image)

    @override_settings(MAX_POST_IMAGE_UPLOAD_SIZE=10)
    def test_oversized_image_rejected(self):
        self.client.force_login(self.author)
        image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")

        response = self.client.post(reverse("post-create"), {"body": "too big", "image": image})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.filter(body="too big").exists())

    def test_editing_a_post_can_replace_its_image(self):
        post = Post.objects.create(author=self.author, body="original")
        self.client.force_login(self.author)
        image = SimpleUploadedFile("new.gif", TINY_GIF, content_type="image/gif")

        self.client.post(reverse("post-edit", args=[post.pk]), {"body": "original", "image": image})

        post.refresh_from_db()
        self.assertIn("new", post.image.name)

    def test_deleting_a_post_clears_the_image_field(self):
        post = Post.objects.create(author=self.author, body="original")
        image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")
        post.image = image
        post.save()
        self.client.force_login(self.author)

        self.client.post(reverse("post-delete", args=[post.pk]))

        post.refresh_from_db()
        self.assertFalse(post.image)

    def test_feed_renders_image_tag_when_post_has_an_image(self):
        post = Post.objects.create(author=self.author, body="with image")
        post.image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")
        post.save()

        response = self.client.get(reverse("feed"))

        self.assertContains(response, "<img")

    def test_feed_does_not_render_image_tag_for_a_post_without_one(self):
        Post.objects.create(author=self.author, body="no image")

        response = self.client.get(reverse("feed"))

        self.assertNotContains(response, "<img")


class FeedPaginationTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        for i in range(8):
            Post.objects.create(author=self.author, body=f"post {i}")

    def test_initial_load_shows_only_first_page(self):
        response = self.client.get(reverse("feed"))
        self.assertEqual(len(response.context["posts"]), 6)

    def test_ajax_request_returns_json_with_remaining_posts_and_next_url(self):
        response = self.client.get(
            reverse("feed"), {"page": 2}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        data = response.json()
        self.assertIn("post 0", data["html"])
        self.assertIsNone(data["next_url"])

    def test_ajax_first_page_has_a_next_url_when_more_remain(self):
        response = self.client.get(reverse("feed"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        data = response.json()
        self.assertIsNotNone(data["next_url"])
        self.assertIn("page=2", data["next_url"])

    def test_normal_request_is_not_json(self):
        response = self.client.get(reverse("feed"))
        self.assertEqual(response["Content-Type"].split(";")[0], "text/html")


class CommentTests(TestCase):
    def test_authenticated_user_can_comment(self):
        author = make_user("alice")
        commenter = make_user("bob")
        post = Post.objects.create(author=author, body="hello")
        self.client.force_login(commenter)
        response = self.client.post(reverse("comment-create", args=[post.pk]), {"body": "nice post"})
        self.assertRedirects(response, reverse("post-detail", args=[post.pk]))
        comment = Comment.objects.get()
        self.assertEqual(comment.author, commenter)
        self.assertEqual(comment.post, post)
        self.assertIsNone(comment.parent)

    def test_reply_sets_parent(self):
        author = make_user("alice")
        post = Post.objects.create(author=author, body="hello")
        top = Comment.objects.create(author=author, post=post, body="top level")
        self.client.force_login(author)
        self.client.post(reverse("comment-create", args=[post.pk]), {"body": "a reply", "parent": top.pk})
        reply = Comment.objects.get(body="a reply")
        self.assertEqual(reply.parent, top)

    def test_comment_tree_builds_multi_level_nesting(self):
        author = make_user("alice")
        post = Post.objects.create(author=author, body="hello")
        root = Comment.objects.create(author=author, post=post, body="root")
        child = Comment.objects.create(author=author, post=post, body="child", parent=root)
        grandchild = Comment.objects.create(author=author, post=post, body="grandchild", parent=child)
        other_root = Comment.objects.create(author=author, post=post, body="other root")

        tree = build_comment_tree(list(Comment.objects.filter(post=post)))

        self.assertEqual([node.body for node in tree], ["root", "other root"])
        root_node = tree[0]
        self.assertEqual([node.body for node in root_node.children], ["child"])
        child_node = root_node.children[0]
        self.assertEqual([node.body for node in child_node.children], ["grandchild"])
        self.assertEqual(child_node.children[0].children, [])
        self.assertEqual(tree[1].children, [])
        self.assertEqual(other_root.parent, None)
        self.assertEqual(grandchild.parent, child)


class CommentEditTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.post = Post.objects.create(author=self.author, body="hello")
        self.comment = Comment.objects.create(author=self.author, post=self.post, body="original")

    def test_author_can_edit_own_comment(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("comment-edit", args=[self.comment.pk]), {"body": "edited"})
        self.comment.refresh_from_db()
        self.assertRedirects(
            response, f"{reverse('post-detail', args=[self.post.pk])}#comment-{self.comment.pk}"
        )
        self.assertEqual(self.comment.body, "edited")
        self.assertTrue(self.comment.edited)

    def test_resubmitting_unchanged_body_does_not_mark_edited(self):
        self.client.force_login(self.author)
        self.client.post(reverse("comment-edit", args=[self.comment.pk]), {"body": "original"})
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.edited)

    def test_non_author_cannot_edit_comment(self):
        other = make_user("mallory")
        self.client.force_login(other)
        response = self.client.post(reverse("comment-edit", args=[self.comment.pk]), {"body": "hacked"})
        self.assertEqual(response.status_code, 404)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.body, "original")
        self.assertFalse(self.comment.edited)

    def test_anonymous_cannot_edit_comment(self):
        response = self.client.post(reverse("comment-edit", args=[self.comment.pk]), {"body": "hacked"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.body, "original")

    def test_invalid_edit_is_ignored(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse("comment-edit", args=[self.comment.pk]), {"body": ""})
        self.comment.refresh_from_db()
        self.assertRedirects(
            response, f"{reverse('post-detail', args=[self.post.pk])}#comment-{self.comment.pk}"
        )
        self.assertEqual(self.comment.body, "original")
        self.assertFalse(self.comment.edited)


class CommentDeleteTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.post = Post.objects.create(author=self.author, body="a post")
        self.comment = Comment.objects.create(author=self.author, post=self.post, body="original")

    def test_author_can_delete_own_comment(self):
        self.client.force_login(self.author)

        response = self.client.post(reverse("comment-delete", args=[self.comment.pk]))

        self.assertRedirects(
            response, f"{reverse('post-detail', args=[self.post.pk])}#comment-{self.comment.pk}"
        )
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.deleted)
        self.assertEqual(self.comment.body, "")

    def test_non_author_cannot_delete_comment(self):
        other = make_user("mallory")
        self.client.force_login(other)

        response = self.client.post(reverse("comment-delete", args=[self.comment.pk]))

        self.assertEqual(response.status_code, 404)
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.deleted)
        self.assertEqual(self.comment.body, "original")

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("comment-delete", args=[self.comment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.deleted)

    def test_deleted_comment_shows_placeholder_instead_of_body(self):
        self.client.force_login(self.author)
        self.client.post(reverse("comment-delete", args=[self.comment.pk]))

        response = self.client.get(reverse("post-detail", args=[self.post.pk]))

        self.assertContains(response, "[deleted]")
        self.assertNotContains(response, "original")

    def test_cannot_edit_an_already_deleted_comment(self):
        self.client.force_login(self.author)
        self.client.post(reverse("comment-delete", args=[self.comment.pk]))

        response = self.client.post(reverse("comment-edit", args=[self.comment.pk]), {"body": "resurrected"})

        self.assertEqual(response.status_code, 404)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.body, "")

    def test_replies_to_a_deleted_comment_stay_intact_and_visible(self):
        reply = Comment.objects.create(
            author=make_user("bob"), post=self.post, parent=self.comment, body="a reply"
        )
        self.client.force_login(self.author)

        self.client.post(reverse("comment-delete", args=[self.comment.pk]))
        response = self.client.get(reverse("post-detail", args=[self.post.pk]))

        self.assertTrue(Comment.objects.filter(pk=reply.pk).exists())
        self.assertContains(response, "a reply")


class CommentPaginationTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.post = Post.objects.create(author=self.author, body="hello")
        self.top_level = [
            Comment.objects.create(author=self.author, post=self.post, body=f"top {i}") for i in range(7)
        ]
        self.reply = Comment.objects.create(
            author=self.author, post=self.post, body="a reply", parent=self.top_level[-1]
        )

    def test_initial_load_shows_only_first_six_top_level_threads(self):
        response = self.client.get(reverse("post-detail", args=[self.post.pk]))
        self.assertEqual(len(response.context["comment_tree"]), 6)
        self.assertTrue(response.context["comments_has_next"])

    def test_ajax_second_page_returns_remaining_thread_with_its_reply(self):
        response = self.client.get(
            reverse("post-detail", args=[self.post.pk]),
            {"page": 2},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        data = response.json()
        self.assertIn("top 6", data["html"])
        self.assertIn("a reply", data["html"])
        self.assertIsNone(data["next_url"])

    def test_reply_to_a_first_page_thread_is_not_paginated_separately(self):
        # Replies live inside their parent's tree node - only top-level
        # comments are paginated, so a reply on an already-shown thread must
        # appear on page 1 alongside it, not wait for its own page.
        reply_to_first = Comment.objects.create(
            author=self.author, post=self.post, body="reply to first", parent=self.top_level[0]
        )
        response = self.client.get(reverse("post-detail", args=[self.post.pk]))
        first_node = response.context["comment_tree"][0]
        self.assertIn(reply_to_first, first_node.children)


class VoteTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.voter = make_user("bob")
        self.post = Post.objects.create(author=self.author, body="hello")
        self.comment = Comment.objects.create(author=self.author, post=self.post, body="a comment")

    def test_anonymous_cannot_vote_on_post(self):
        before = PostVote.objects.count()
        response = self.client.post(reverse("post-upvote", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PostVote.objects.count(), before)

    def test_upvote_creates_vote(self):
        self.client.force_login(self.voter)
        self.client.post(reverse("post-upvote", args=[self.post.pk]))
        vote = PostVote.objects.get(user=self.voter, post=self.post)
        self.assertEqual(vote.value, PostVote.UP)

    def test_clicking_same_direction_again_removes_vote(self):
        self.client.force_login(self.voter)
        self.client.post(reverse("post-upvote", args=[self.post.pk]))
        self.client.post(reverse("post-upvote", args=[self.post.pk]))
        self.assertFalse(PostVote.objects.filter(user=self.voter, post=self.post).exists())

    def test_switching_direction_updates_vote(self):
        self.client.force_login(self.voter)
        self.client.post(reverse("post-upvote", args=[self.post.pk]))
        self.client.post(reverse("post-downvote", args=[self.post.pk]))
        vote = PostVote.objects.get(user=self.voter, post=self.post)
        self.assertEqual(vote.value, PostVote.DOWN)
        self.assertEqual(PostVote.objects.filter(user=self.voter, post=self.post).count(), 1)

    def test_post_score_reflects_votes(self):
        third = make_user("carol")
        PostVote.objects.create(user=self.voter, post=self.post, value=PostVote.UP)
        PostVote.objects.create(user=third, post=self.post, value=PostVote.DOWN)
        response = self.client.get(reverse("post-detail", args=[self.post.pk]))
        # +1 from the author's automatic self-upvote, +1 voter, -1 third.
        self.assertEqual(response.context["post"].score, 1)

    def test_comment_vote_toggle(self):
        self.client.force_login(self.voter)
        self.client.post(reverse("comment-upvote", args=[self.comment.pk]))
        self.assertEqual(
            CommentVote.objects.get(user=self.voter, comment=self.comment).value, CommentVote.UP
        )
        self.client.post(reverse("comment-upvote", args=[self.comment.pk]))
        self.assertFalse(CommentVote.objects.filter(user=self.voter, comment=self.comment).exists())

    def test_anonymous_cannot_vote_on_comment(self):
        before = CommentVote.objects.count()
        response = self.client.post(reverse("comment-upvote", args=[self.comment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CommentVote.objects.count(), before)

    def test_new_post_is_automatically_upvoted_by_its_author(self):
        vote = PostVote.objects.get(user=self.author, post=self.post)
        self.assertEqual(vote.value, PostVote.UP)
        self.assertEqual(self.post.votes.count(), 1)

    def test_new_comment_is_automatically_upvoted_by_its_author(self):
        vote = CommentVote.objects.get(user=self.author, comment=self.comment)
        self.assertEqual(vote.value, CommentVote.UP)
        self.assertEqual(self.comment.votes.count(), 1)

    def test_editing_a_post_does_not_add_a_second_self_vote(self):
        self.post.body = "edited"
        self.post.save()
        self.assertEqual(PostVote.objects.filter(user=self.author, post=self.post).count(), 1)


class ToggleReactionTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.reactor = make_user("bob")
        self.post = Post.objects.create(author=self.author, body="hello")

    def test_reacting_creates_a_row(self):
        toggle_reaction(PostReaction, {"post": self.post}, self.reactor, PostReaction.Emoji.THUMBSUP)
        reaction = PostReaction.objects.get(user=self.reactor, post=self.post)
        self.assertEqual(reaction.emoji, PostReaction.Emoji.THUMBSUP)

    def test_reacting_with_the_same_emoji_again_removes_it(self):
        toggle_reaction(PostReaction, {"post": self.post}, self.reactor, PostReaction.Emoji.THUMBSUP)
        toggle_reaction(PostReaction, {"post": self.post}, self.reactor, PostReaction.Emoji.THUMBSUP)
        self.assertFalse(PostReaction.objects.filter(user=self.reactor, post=self.post).exists())

    def test_reacting_with_a_different_emoji_switches_it_in_place(self):
        toggle_reaction(PostReaction, {"post": self.post}, self.reactor, PostReaction.Emoji.THUMBSUP)
        toggle_reaction(PostReaction, {"post": self.post}, self.reactor, PostReaction.Emoji.HEART)
        self.assertEqual(PostReaction.objects.filter(user=self.reactor, post=self.post).count(), 1)
        reaction = PostReaction.objects.get(user=self.reactor, post=self.post)
        self.assertEqual(reaction.emoji, PostReaction.Emoji.HEART)


class PostReactionViewTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.reactor = make_user("bob")
        self.post = Post.objects.create(author=self.author, body="hello")

    def test_authenticated_user_can_react(self):
        self.client.force_login(self.reactor)
        self.client.post(reverse("post-react", args=[self.post.pk]), {"emoji": "thumbsup"})
        self.assertTrue(PostReaction.objects.filter(user=self.reactor, post=self.post, emoji="thumbsup").exists())

    def test_invalid_emoji_is_ignored(self):
        self.client.force_login(self.reactor)
        self.client.post(reverse("post-react", args=[self.post.pk]), {"emoji": "not-a-real-emoji"})
        self.assertFalse(PostReaction.objects.filter(user=self.reactor, post=self.post).exists())

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("post-react", args=[self.post.pk]), {"emoji": "thumbsup"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertFalse(PostReaction.objects.exists())

    def test_author_can_react_to_own_post(self):
        self.client.force_login(self.author)
        self.client.post(reverse("post-react", args=[self.post.pk]), {"emoji": "party"})
        self.assertTrue(PostReaction.objects.filter(user=self.author, post=self.post, emoji="party").exists())


class GroupReactionsFilterTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.viewer = make_user("bob")
        self.other = make_user("carol")
        self.post = Post.objects.create(author=self.author, body="hello")

    def test_counts_are_correct_per_emoji(self):
        PostReaction.objects.create(user=self.viewer, post=self.post, emoji="thumbsup")
        PostReaction.objects.create(user=self.other, post=self.post, emoji="thumbsup")
        result = group_reactions(self.post.reactions.all(), self.viewer)
        thumbsup = next(r for r in result if r["value"] == "thumbsup")
        self.assertEqual(thumbsup["count"], 2)

    def test_mine_is_set_only_for_the_viewers_own_reaction(self):
        PostReaction.objects.create(user=self.viewer, post=self.post, emoji="heart")
        PostReaction.objects.create(user=self.other, post=self.post, emoji="thumbsup")
        result = group_reactions(self.post.reactions.all(), self.viewer)
        mine_flags = {r["value"]: r["mine"] for r in result}
        self.assertTrue(mine_flags["heart"])
        self.assertFalse(mine_flags["thumbsup"])

    def test_anonymous_viewer_never_gets_mine_true(self):
        PostReaction.objects.create(user=self.other, post=self.post, emoji="thumbsup")
        anonymous = AnonymousUser()
        result = group_reactions(self.post.reactions.all(), anonymous)
        self.assertFalse(any(r["mine"] for r in result))

    def test_returns_all_six_emoji_even_with_zero_count(self):
        result = group_reactions(self.post.reactions.all(), self.viewer)
        self.assertEqual(len(result), 6)
        self.assertTrue(all(r["count"] == 0 for r in result))


class PostReactionRenderingTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.reactor = make_user("bob")
        self.post = Post.objects.create(author=self.author, body="hello")
        PostReaction.objects.create(user=self.reactor, post=self.post, emoji="thumbsup")

    def test_feed_shows_reaction_count_and_highlights_mine(self):
        self.client.force_login(self.reactor)
        response = self.client.get(reverse("feed"))
        self.assertContains(response, "👍 1")

    def test_post_detail_shows_reaction_count(self):
        self.client.force_login(self.author)
        response = self.client.get(reverse("post-detail", args=[self.post.pk]))
        self.assertContains(response, "👍 1")

    def test_anonymous_visitor_sees_no_reaction_buttons(self):
        response = self.client.get(reverse("post-detail", args=[self.post.pk]))
        self.assertNotContains(response, "post-react")


class MarkdownRenderingTests(TestCase):
    def test_heading_renders(self):
        self.assertIn("<h1>Title</h1>", render_markdown("# Title"))

    def test_bold_renders(self):
        self.assertIn("<strong>bold</strong>", render_markdown("**bold**"))

    def test_list_renders(self):
        html = render_markdown("- one\n- two")
        self.assertIn("<ul>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<li>two</li>", html)

    def test_fenced_code_block_renders(self):
        html = render_markdown("```\ncode here\n```")
        self.assertIn("<pre><code>", html)
        self.assertIn("code here", html)

    def test_fenced_code_block_with_language_gets_syntax_highlighted(self):
        html = render_markdown("```python\ndef greet():\n    return 'hi'\n```")
        self.assertIn('<pre class="highlight">', html)
        self.assertIn('<code class="language-python">', html)
        # "def" is a Pygments Keyword ("k") for Python.
        self.assertIn('<span class="k">def</span>', html)

    def test_fenced_code_block_with_unknown_language_falls_back_to_plain(self):
        html = render_markdown("```not-a-real-language\nsome text\n```")
        self.assertNotIn('class="highlight"', html)
        self.assertIn("some text", html)

    def test_highlighted_code_cannot_break_out_of_the_block(self):
        html = render_markdown("```python\n'</code></pre><script>alert(1)</script>'\n```")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_script_tag_is_stripped(self):
        html = render_markdown("<script>alert('xss')</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_javascript_href_is_stripped(self):
        html = render_markdown("[click me](javascript:evil)")
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn("<a ", html)

    def test_onerror_attribute_is_stripped(self):
        html = render_markdown('<img src=x onerror="alert(1)">')
        self.assertNotIn("<img", html)

    def test_raw_html_passthrough_is_stripped(self):
        html = render_markdown('<div onclick="evil()">hello</div>')
        self.assertNotIn("<div", html)

    def test_links_get_nofollow_noopener(self):
        html = render_markdown("[link](https://example.com)")
        self.assertIn('rel="nofollow noopener"', html)


class ConversationModelTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_get_or_create_returns_same_conversation_regardless_of_order(self):
        first = get_or_create_conversation(self.alice, self.bob)
        second = get_or_create_conversation(self.bob, self.alice)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_self_conversation_rejected_at_db_level(self):
        lo, hi = sorted([self.alice, self.alice], key=lambda u: u.pk)
        with self.assertRaises(IntegrityError):
            Conversation.objects.create(user1=lo, user2=hi)


class StartConversationViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_creates_and_redirects_to_conversation(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("conversation-start", args=["bob"]))
        conversation = Conversation.objects.get()
        self.assertRedirects(response, reverse("conversation-detail", args=[conversation.pk]))

    def test_reuses_existing_conversation_started_from_either_side(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("conversation-start", args=["bob"]))
        self.client.force_login(self.bob)
        self.client.post(reverse("conversation-start", args=["alice"]))

        self.assertEqual(Conversation.objects.count(), 1)

    def test_cannot_message_self(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("conversation-start", args=["alice"]))
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertRedirects(response, reverse("profile", args=["alice"]))

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("conversation-start", args=["bob"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_cannot_message_a_user_you_blocked(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.client.force_login(self.alice)

        response = self.client.post(reverse("conversation-start", args=["bob"]))

        self.assertEqual(Conversation.objects.count(), 0)
        self.assertRedirects(response, reverse("profile", args=["bob"]))

    def test_cannot_message_a_user_who_blocked_you(self):
        Block.objects.create(blocker=self.bob, blocked=self.alice)
        self.client.force_login(self.alice)

        response = self.client.post(reverse("conversation-start", args=["bob"]))

        self.assertEqual(Conversation.objects.count(), 0)


class ConversationPrivacyTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.mallory = make_user("mallory")
        self.conversation = get_or_create_conversation(self.alice, self.bob)
        Message.objects.create(conversation=self.conversation, sender=self.alice, body="hi bob")

    def test_participant_can_view(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hi bob")

    def test_non_participant_cannot_view(self):
        self.client.force_login(self.mallory)
        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_non_participant_cannot_send_message(self):
        self.client.force_login(self.mallory)
        response = self.client.post(
            reverse("message-send", args=[self.conversation.pk]), {"body": "sneaky"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Message.objects.filter(body="sneaky").exists())


class MessageSendViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.conversation = get_or_create_conversation(self.alice, self.bob)

    def test_participant_can_send_message(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("message-send", args=[self.conversation.pk]), {"body": "hello there"}
        )
        self.assertRedirects(response, reverse("conversation-detail", args=[self.conversation.pk]))
        message = Message.objects.get()
        self.assertEqual(message.sender, self.alice)
        self.assertEqual(message.body, "hello there")
        self.assertFalse(message.read)

    def test_blank_message_is_not_created(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("message-send", args=[self.conversation.pk]), {"body": ""})
        self.assertEqual(Message.objects.count(), 0)

    def test_cannot_send_in_a_conversation_after_being_blocked(self):
        Block.objects.create(blocker=self.bob, blocked=self.alice)
        self.client.force_login(self.alice)

        self.client.post(reverse("message-send", args=[self.conversation.pk]), {"body": "hello?"})

        self.assertEqual(Message.objects.count(), 0)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(
            reverse("message-send", args=[self.conversation.pk]), {"body": "hello"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Message.objects.count(), 0)


class MessageImageTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.conversation = get_or_create_conversation(self.alice, self.bob)
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

    def test_sending_an_image_only_message_succeeds(self):
        self.client.force_login(self.alice)
        image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")

        response = self.client.post(
            reverse("message-send", args=[self.conversation.pk]), {"body": "", "image": image}
        )

        self.assertRedirects(response, reverse("conversation-detail", args=[self.conversation.pk]))
        message = Message.objects.get()
        self.assertEqual(message.body, "")
        self.assertTrue(message.image)

    def test_sending_a_message_with_body_and_image_succeeds(self):
        self.client.force_login(self.alice)
        image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")

        self.client.post(
            reverse("message-send", args=[self.conversation.pk]), {"body": "look at this", "image": image}
        )

        message = Message.objects.get()
        self.assertEqual(message.body, "look at this")
        self.assertTrue(message.image)

    def test_sending_with_neither_body_nor_image_is_rejected(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("message-send", args=[self.conversation.pk]), {"body": ""})

        self.assertEqual(Message.objects.count(), 0)

    @override_settings(MAX_MESSAGE_IMAGE_UPLOAD_SIZE=10)
    def test_oversized_image_rejected(self):
        self.client.force_login(self.alice)
        image = SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif")

        self.client.post(
            reverse("message-send", args=[self.conversation.pk]), {"body": "", "image": image}
        )

        self.assertEqual(Message.objects.count(), 0)

    def test_conversation_page_renders_image_tag_for_a_message_with_one(self):
        Message.objects.create(
            conversation=self.conversation,
            sender=self.alice,
            image=SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif"),
        )
        self.client.force_login(self.bob)

        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))

        self.assertContains(response, "<img")

    def test_conversation_page_does_not_render_image_tag_for_a_text_only_message(self):
        Message.objects.create(conversation=self.conversation, sender=self.alice, body="just text")
        self.client.force_login(self.bob)

        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))

        self.assertNotContains(response, "<img")

    def test_image_only_message_does_not_render_an_empty_body_div(self):
        Message.objects.create(
            conversation=self.conversation,
            sender=self.alice,
            image=SimpleUploadedFile("photo.gif", TINY_GIF, content_type="image/gif"),
        )
        self.client.force_login(self.bob)

        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))

        self.assertNotContains(response, "message-body")


class MessageMarkdownRenderingTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.conversation = get_or_create_conversation(self.alice, self.bob)

    def test_message_body_renders_markdown(self):
        Message.objects.create(conversation=self.conversation, sender=self.alice, body="**bold** and *italic*")
        self.client.force_login(self.bob)

        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))

        self.assertContains(response, "<strong>bold</strong>")
        self.assertContains(response, "<em>italic</em>")

    def test_message_body_strips_script_tags(self):
        Message.objects.create(
            conversation=self.conversation, sender=self.alice, body="<script>alert('xss')</script>"
        )
        self.client.force_login(self.bob)

        response = self.client.get(reverse("conversation-detail", args=[self.conversation.pk]))

        # The page legitimately has other <script src="..."> tags (badge
        # polling JS), so check the malicious payload specifically rather
        # than asserting no "<script>" substring appears anywhere at all.
        self.assertNotContains(response, "<script>alert")
        self.assertContains(response, "&lt;script&gt;")


class UnreadMessageCountTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")

    def test_counts_only_messages_from_others_not_yet_read(self):
        convo_with_bob = get_or_create_conversation(self.alice, self.bob)
        convo_with_carol = get_or_create_conversation(self.alice, self.carol)
        Message.objects.create(conversation=convo_with_bob, sender=self.bob, body="from bob")
        Message.objects.create(conversation=convo_with_carol, sender=self.carol, body="from carol")
        Message.objects.create(conversation=convo_with_bob, sender=self.alice, body="from alice")

        self.assertEqual(unread_message_count(self.alice), 2)
        self.assertEqual(unread_message_count(self.bob), 1)

    def test_viewing_conversation_marks_messages_read_and_updates_count(self):
        conversation = get_or_create_conversation(self.alice, self.bob)
        Message.objects.create(conversation=conversation, sender=self.bob, body="hi")
        self.assertEqual(unread_message_count(self.alice), 1)

        self.client.force_login(self.alice)
        self.client.get(reverse("conversation-detail", args=[conversation.pk]))

        self.assertEqual(unread_message_count(self.alice), 0)
        self.assertTrue(Message.objects.get().read)

    def test_viewing_own_conversation_does_not_mark_own_messages_read_differently(self):
        conversation = get_or_create_conversation(self.alice, self.bob)
        Message.objects.create(conversation=conversation, sender=self.alice, body="hi bob")

        self.client.force_login(self.bob)
        self.client.get(reverse("conversation-detail", args=[conversation.pk]))

        # bob viewing marks alice's message (sent to him) as read...
        self.assertTrue(Message.objects.get().read)
        # ...and it was never counted as unread for alice (its own sender) anyway.
        self.assertEqual(unread_message_count(self.alice), 0)

    def test_endpoint_returns_json_count(self):
        conversation = get_or_create_conversation(self.alice, self.bob)
        Message.objects.create(conversation=conversation, sender=self.bob, body="hi")

        self.client.force_login(self.alice)
        response = self.client.get(reverse("unread-message-count"))

        self.assertEqual(response.json(), {"count": 1})

    def test_anonymous_cannot_access_unread_count_endpoint(self):
        response = self.client.get(reverse("unread-message-count"))
        self.assertEqual(response.status_code, 302)


class ConversationListViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")

    def test_lists_only_the_users_own_conversations_with_other_participant_and_unread_count(self):
        mine = get_or_create_conversation(self.alice, self.bob)
        get_or_create_conversation(self.bob, self.carol)
        Message.objects.create(conversation=mine, sender=self.bob, body="hi")

        self.client.force_login(self.alice)
        response = self.client.get(reverse("conversation-list"))

        conversations = list(response.context["conversations"])
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0].other, self.bob)
        self.assertEqual(conversations[0].unread_count, 1)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("conversation-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class MentionExtractionTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_finds_a_real_mentioned_user(self):
        users = extract_mentioned_users(f"hey @{self.bob.username}, check this out")
        self.assertEqual(users, [self.bob])

    def test_ignores_a_mention_of_a_nonexistent_username(self):
        users = extract_mentioned_users("hey @not-a-real-user")
        self.assertEqual(users, [])

    def test_matches_case_insensitively(self):
        users = extract_mentioned_users(f"hey @{self.bob.username.upper()}")
        self.assertEqual(users, [self.bob])

    def test_deduplicates_repeated_mentions(self):
        users = extract_mentioned_users(f"@{self.bob.username} again, @{self.bob.username}!")
        self.assertEqual(users, [self.bob])

    def test_excludes_the_given_user(self):
        users = extract_mentioned_users(f"@{self.alice.username} @{self.bob.username}", exclude=self.alice)
        self.assertEqual(users, [self.bob])

    def test_body_with_no_mentions_returns_empty_list(self):
        self.assertEqual(extract_mentioned_users("nothing to see here"), [])


class HashtagExtractionTests(TestCase):
    def test_finds_a_simple_hashtag(self):
        self.assertEqual(extract_hashtag_names("check out #django"), {"django"})

    def test_deduplicates_case_insensitively(self):
        self.assertEqual(extract_hashtag_names("#Django and #django again"), {"django"})

    def test_does_not_match_hash_preceded_by_a_word_character(self):
        self.assertEqual(extract_hashtag_names("I love C#"), set())

    def test_does_not_match_an_atx_heading(self):
        self.assertEqual(extract_hashtag_names("# Heading"), set())
        self.assertEqual(extract_hashtag_names("## Subheading"), set())

    def test_finds_several_distinct_tags(self):
        self.assertEqual(extract_hashtag_names("#chatter is #awesome and #fun"), {"chatter", "awesome", "fun"})

    def test_body_with_no_hashtags_returns_empty_set(self):
        self.assertEqual(extract_hashtag_names("nothing to see here"), set())

    def test_does_not_extract_hash_inside_inline_code(self):
        self.assertEqual(extract_hashtag_names("use `#include` in C"), set())

    def test_does_not_extract_hash_inside_a_fenced_code_block(self):
        self.assertEqual(extract_hashtag_names("```python\n# not a tag\n```"), set())

    def test_still_extracts_a_real_hashtag_alongside_code(self):
        self.assertEqual(extract_hashtag_names("check out #django, and `#include` too"), {"django"})


class MarkdownHashtagRenderingTests(TestCase):
    def test_hashtag_renders_as_a_link(self):
        html = render_markdown("check out #django")
        self.assertIn('<a href="/tags/django/" rel="nofollow noopener">#django</a>', html)

    def test_link_text_preserves_original_casing(self):
        html = render_markdown("#DjangoTips")
        self.assertIn('<a href="/tags/djangotips/" rel="nofollow noopener">#DjangoTips</a>', html)

    def test_atx_heading_still_renders_as_a_heading(self):
        html = render_markdown("# Heading")
        self.assertIn("<h1>Heading</h1>", html)
        self.assertNotIn('<a href="/tags/', html)

    def test_hash_inside_fenced_code_block_is_not_linkified(self):
        html = render_markdown("```python\n# not a tag\n```")
        self.assertNotIn('<a href="/tags/', html)

    def test_hash_inside_inline_code_is_not_linkified(self):
        html = render_markdown("use `#define` in C")
        self.assertNotIn('<a href="/tags/', html)

    def test_hashtag_inside_an_existing_link_does_not_nest_anchors(self):
        html = render_markdown("[check out #django](https://example.com)")
        self.assertEqual(html.count("<a "), 1)

    def test_linkify_hashtags_false_leaves_hashtags_as_plain_text(self):
        html = render_markdown("check out #django", linkify_hashtags=False)
        self.assertNotIn("<a ", html)
        self.assertIn("#django", html)


class PostCardHashtagRenderingTests(TestCase):
    def test_feed_card_does_not_nest_anchors_for_a_hashtagged_first_line(self):
        author = make_user("alice")
        Post.objects.create(author=author, body="#django is great")

        response = self.client.get(reverse("feed"))

        # markdown_preview (used for the card's clickable first-line preview,
        # itself wrapped in an <a> to the post) must not also emit a hashtag
        # <a> - that would nest anchors, which browsers "fix" by splitting
        # the outer link into dead fragments.
        self.assertNotIn("/tags/django/", response.content.decode())
        self.assertContains(response, "#django")


class PostTagSyncTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")

    def test_creating_a_post_associates_its_hashtags(self):
        self.client.force_login(self.author)

        self.client.post(reverse("post-create"), {"body": "#django and #Flask"})

        post = Post.objects.get(body="#django and #Flask")
        self.assertEqual(set(post.tags.values_list("name", flat=True)), {"django", "flask"})

    def test_editing_a_post_to_remove_a_tag_detaches_it(self):
        post = Post.objects.create(author=self.author, body="#django and #flask")
        post.tags.set([Tag.objects.get_or_create(name="django")[0], Tag.objects.get_or_create(name="flask")[0]])
        self.client.force_login(self.author)

        self.client.post(reverse("post-edit", args=[post.pk]), {"body": "#django only now"})

        post.refresh_from_db()
        self.assertEqual(set(post.tags.values_list("name", flat=True)), {"django"})

    def test_two_posts_with_the_same_tag_share_one_tag_row(self):
        self.client.force_login(self.author)

        self.client.post(reverse("post-create"), {"body": "first #shared"})
        self.client.post(reverse("post-create"), {"body": "second #shared"})

        self.assertEqual(Tag.objects.filter(name="shared").count(), 1)


class TagDetailViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_shows_only_non_deleted_posts_with_the_tag(self):
        tagged = Post.objects.create(author=self.alice, body="#chatter is great")
        tagged.tags.set([Tag.objects.get_or_create(name="chatter")[0]])
        deleted = Post.objects.create(author=self.alice, body="#chatter deleted", deleted=True)
        deleted.tags.set([Tag.objects.get_or_create(name="chatter")[0]])
        Post.objects.create(author=self.alice, body="no tag here")

        response = self.client.get(reverse("tag-detail", args=["chatter"]))

        self.assertEqual(list(response.context["posts"]), [tagged])

    def test_excludes_muted_or_blocked_authors_posts(self):
        post = Post.objects.create(author=self.bob, body="#chatter")
        post.tags.set([Tag.objects.get_or_create(name="chatter")[0]])
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("tag-detail", args=["chatter"]))

        self.assertNotIn(post, response.context["posts"])

    def test_unused_tag_name_renders_an_empty_state_not_a_404(self):
        response = self.client.get(reverse("tag-detail", args=["neverused"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["posts"]), [])

    def test_pagination_spans_a_second_page(self):
        tag = Tag.objects.get_or_create(name="popular")[0]
        for i in range(8):
            post = Post.objects.create(author=self.alice, body=f"post {i} #popular")
            post.tags.set([tag])

        response = self.client.get(reverse("tag-detail", args=["popular"]))

        self.assertTrue(response.context["page_obj"].has_next())


class TagIndexViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")

    def test_tags_ordered_by_post_count_descending_ties_broken_by_name(self):
        popular = Tag.objects.get_or_create(name="popular")[0]
        rare = Tag.objects.get_or_create(name="rare")[0]
        also_rare = Tag.objects.get_or_create(name="alsorare")[0]
        for i in range(3):
            post = Post.objects.create(author=self.alice, body=f"post {i} #popular")
            post.tags.set([popular])
        Post.objects.create(author=self.alice, body="one #rare").tags.set([rare])
        Post.objects.create(author=self.alice, body="one #alsorare").tags.set([also_rare])

        response = self.client.get(reverse("tag-index"))

        self.assertEqual([t.name for t in response.context["tags"]], ["popular", "alsorare", "rare"])

    def test_tag_with_only_deleted_posts_does_not_appear(self):
        tag = Tag.objects.get_or_create(name="gone")[0]
        post = Post.objects.create(author=self.alice, body="#gone", deleted=True)
        post.tags.set([tag])

        response = self.client.get(reverse("tag-index"))

        self.assertNotIn(tag, response.context["tags"])

    def test_count_reflects_only_non_deleted_posts(self):
        tag = Tag.objects.get_or_create(name="mixed")[0]
        live = Post.objects.create(author=self.alice, body="#mixed live")
        live.tags.set([tag])
        deleted = Post.objects.create(author=self.alice, body="#mixed deleted", deleted=True)
        deleted.tags.set([tag])

        response = self.client.get(reverse("tag-index"))

        result_tag = next(t for t in response.context["tags"] if t.name == "mixed")
        self.assertEqual(result_tag.post_count, 1)

    def test_tag_never_used_by_any_post_does_not_appear(self):
        Tag.objects.get_or_create(name="unused")

        response = self.client.get(reverse("tag-index"))

        self.assertEqual(list(response.context["tags"]), [])

    def test_pagination_spans_a_second_page(self):
        for i in range(25):
            tag = Tag.objects.get_or_create(name=f"tag{i}")[0]
            post = Post.objects.create(author=self.alice, body=f"post {i}")
            post.tags.set([tag])

        response = self.client.get(reverse("tag-index"))

        self.assertTrue(response.context["page_obj"].has_next())

    def test_tag_detail_page_links_back_to_the_index(self):
        tag = Tag.objects.get_or_create(name="chatter")[0]
        post = Post.objects.create(author=self.alice, body="#chatter")
        post.tags.set([tag])

        response = self.client.get(reverse("tag-detail", args=["chatter"]))

        self.assertContains(response, reverse("tag-index"))


class TagSearchViewTests(TestCase):
    def setUp(self):
        self.viewer = make_user("dave")
        Tag.objects.create(name="chatter")
        Tag.objects.create(name="chat")
        Tag.objects.create(name="django")

    def test_anonymous_user_cannot_search(self):
        response = self.client.get(reverse("tag-search"), {"q": "cha"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_prefix_match_is_case_insensitive(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("tag-search"), {"q": "CHA"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"names": ["chat", "chatter"]})

    def test_non_matching_query_returns_empty_list(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("tag-search"), {"q": "zzz"})

        self.assertEqual(response.json(), {"names": []})

    def test_empty_query_returns_empty_list(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("tag-search"), {"q": ""})

        self.assertEqual(response.json(), {"names": []})


class MentionNotificationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_creating_a_post_notifies_a_mentioned_user(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("post-create"), {"body": f"hi @{self.bob.username}"})

        notification = Notification.objects.get()
        self.assertEqual(notification.kind, Notification.Kind.MENTION)
        self.assertEqual(notification.recipient, self.bob)
        self.assertEqual(notification.actor, self.alice)
        self.assertIsNone(notification.comment)

    def test_creating_a_comment_notifies_a_mentioned_user(self):
        post = Post.objects.create(author=self.alice, body="a post")
        self.client.force_login(self.alice)

        self.client.post(reverse("comment-create", args=[post.pk]), {"body": f"hi @{self.bob.username}"})

        mention = Notification.objects.get(kind=Notification.Kind.MENTION)
        self.assertEqual(mention.recipient, self.bob)
        self.assertEqual(mention.post, post)
        self.assertEqual(mention.comment, Comment.objects.get())

    def test_mentioning_yourself_creates_no_notification(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("post-create"), {"body": f"note to self @{self.alice.username}"})

        self.assertFalse(Notification.objects.exists())

    def test_editing_a_post_to_add_a_mention_does_not_notify(self):
        post = Post.objects.create(author=self.alice, body="no mentions here")
        self.client.force_login(self.alice)

        self.client.post(reverse("post-edit", args=[post.pk]), {"body": f"now mentioning @{self.bob.username}"})

        self.assertFalse(Notification.objects.exists())


class NotificationListViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body=f"hi @{self.bob.username}")
        self.notification = Notification.objects.create(recipient=self.bob, actor=self.alice, post=self.post)

    def test_shows_only_the_viewers_own_notifications(self):
        other_post = Post.objects.create(author=self.bob, body="unrelated")
        Notification.objects.create(recipient=self.alice, actor=self.bob, post=other_post)
        self.client.force_login(self.bob)

        response = self.client.get(reverse("notification-list"))

        notifications = list(response.context["notifications"])
        self.assertEqual(notifications, [self.notification])

    def test_viewing_marks_notifications_read(self):
        self.client.force_login(self.bob)
        self.assertEqual(unread_notification_count(self.bob), 1)

        self.client.get(reverse("notification-list"))

        self.assertEqual(unread_notification_count(self.bob), 0)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("notification-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class NotificationListRenderingTests(TestCase):
    # Regression coverage for a real bug: an early draft of the template used
    # a `{# ... #}` single-line comment spanning multiple lines, which Django
    # doesn't strip - it rendered as literal text on the page. Caught via a
    # live browser check, not by a test, since assertContains on the expected
    # phrase alone still passed (the comment text just appeared *before* it).
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")
        self.comment = Comment.objects.create(author=self.alice, post=self.post, body="a comment")
        self.reply = Comment.objects.create(author=self.bob, post=self.post, parent=self.comment, body="a reply")
        self.client.force_login(self.alice)

    def render(self, **kwargs):
        Notification.objects.create(recipient=self.alice, actor=self.bob, post=self.post, **kwargs)
        return self.client.get(reverse("notification-list"))

    def test_no_stray_template_comment_text_leaks_into_the_page(self):
        response = self.render(kind=Notification.Kind.REPLY, comment=self.reply)
        self.assertNotContains(response, "matters for the wording")

    def test_mention_in_a_post_wording(self):
        response = self.render(kind=Notification.Kind.MENTION)
        self.assertContains(response, "mentioned you in a post")

    def test_mention_in_a_comment_wording(self):
        response = self.render(kind=Notification.Kind.MENTION, comment=self.comment)
        self.assertContains(response, "mentioned you in a comment")

    def test_top_level_reply_wording_says_post(self):
        top_level_reply = Comment.objects.create(author=self.bob, post=self.post, body="top level")
        response = self.render(kind=Notification.Kind.REPLY, comment=top_level_reply)
        self.assertContains(response, "replied to your post")

    def test_nested_reply_wording_says_comment(self):
        response = self.render(kind=Notification.Kind.REPLY, comment=self.reply)
        self.assertContains(response, "replied to your comment")

    def test_upvote_on_a_post_wording(self):
        response = self.render(kind=Notification.Kind.UPVOTE)
        self.assertContains(response, "upvoted your post")

    def test_upvote_on_a_comment_wording(self):
        response = self.render(kind=Notification.Kind.UPVOTE, comment=self.comment)
        self.assertContains(response, "upvoted your comment")


class NotificationDismissViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")
        self.notification = Notification.objects.create(recipient=self.alice, actor=self.bob, post=self.post)

    def test_dismissing_hides_it_from_the_list(self):
        self.client.force_login(self.alice)

        response = self.client.post(reverse("notification-dismiss", args=[self.notification.pk]))

        self.assertRedirects(response, reverse("notification-list"))
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.dismissed)
        list_response = self.client.get(reverse("notification-list"))
        self.assertNotIn(self.notification, list_response.context["notifications"])

    def test_cannot_dismiss_someone_elses_notification(self):
        carol = make_user("carol")
        self.client.force_login(carol)

        response = self.client.post(reverse("notification-dismiss", args=[self.notification.pk]))

        self.assertEqual(response.status_code, 404)
        self.notification.refresh_from_db()
        self.assertFalse(self.notification.dismissed)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("notification-dismiss", args=[self.notification.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_dismissing_marks_it_read_too_since_viewing_the_list_already_did(self):
        # Dismiss is only ever reachable from the notification list page,
        # which marks everything read before rendering - so by the time a
        # notification can be dismissed, it's already read by construction.
        self.client.force_login(self.alice)
        self.client.get(reverse("notification-list"))

        self.client.post(reverse("notification-dismiss", args=[self.notification.pk]))

        self.notification.refresh_from_db()
        self.assertTrue(self.notification.read)
        self.assertTrue(self.notification.dismissed)


class NotificationDismissAllViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")
        self.first = Notification.objects.create(recipient=self.alice, actor=self.bob, post=self.post)
        self.second = Notification.objects.create(recipient=self.alice, actor=self.bob, post=self.post)

    def test_dismisses_every_notification_for_the_current_user(self):
        self.client.force_login(self.alice)

        response = self.client.post(reverse("notification-dismiss-all"))

        self.assertRedirects(response, reverse("notification-list"))
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertTrue(self.first.dismissed)
        self.assertTrue(self.second.dismissed)

    def test_does_not_affect_another_users_notifications(self):
        other_post = Post.objects.create(author=self.bob, body="unrelated")
        others = Notification.objects.create(recipient=self.bob, actor=self.alice, post=other_post)
        self.client.force_login(self.alice)

        self.client.post(reverse("notification-dismiss-all"))

        others.refresh_from_db()
        self.assertFalse(others.dismissed)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("notification-dismiss-all"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_dismiss_all_button_hidden_when_there_are_no_notifications(self):
        carol = make_user("carol")
        self.client.force_login(carol)

        response = self.client.get(reverse("notification-list"))

        self.assertNotContains(response, "Dismiss all")


class UnreadNotificationCountViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        post = Post.objects.create(author=self.alice, body=f"hi @{self.bob.username}")
        Notification.objects.create(recipient=self.bob, actor=self.alice, post=post)

    def test_returns_the_viewers_unread_count(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("unread-notification-count"))
        self.assertEqual(response.json(), {"count": 1})

    def test_anonymous_cannot_access_unread_count_endpoint(self):
        response = self.client.get(reverse("unread-notification-count"))
        self.assertEqual(response.status_code, 302)


class ToggleVoteReturnValueTests(TestCase):
    def setUp(self):
        self.author = make_user("alice")
        self.voter = make_user("bob")
        self.post = Post.objects.create(author=self.author, body="hello")

    def test_new_vote_returns_created(self):
        self.assertEqual(toggle_vote(PostVote, {"post": self.post}, self.voter, PostVote.UP), "created")

    def test_repeating_the_same_vote_returns_removed(self):
        toggle_vote(PostVote, {"post": self.post}, self.voter, PostVote.UP)
        self.assertEqual(toggle_vote(PostVote, {"post": self.post}, self.voter, PostVote.UP), "removed")

    def test_opposite_vote_returns_flipped(self):
        toggle_vote(PostVote, {"post": self.post}, self.voter, PostVote.DOWN)
        self.assertEqual(toggle_vote(PostVote, {"post": self.post}, self.voter, PostVote.UP), "flipped")


class ReplyNotificationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")

    def test_top_level_comment_notifies_the_post_author(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-create", args=[self.post.pk]), {"body": "nice post"})

        notification = Notification.objects.get(kind=Notification.Kind.REPLY)
        self.assertEqual(notification.recipient, self.alice)
        self.assertEqual(notification.actor, self.bob)
        self.assertEqual(notification.comment, Comment.objects.get())

    def test_reply_to_a_comment_notifies_the_comments_author_not_the_post_author(self):
        carol = make_user("carol")
        top_level = Comment.objects.create(author=self.bob, post=self.post, body="first")
        self.client.force_login(carol)

        self.client.post(
            reverse("comment-create", args=[self.post.pk]),
            {"body": "replying to you", "parent": top_level.pk},
        )

        notification = Notification.objects.get(kind=Notification.Kind.REPLY)
        self.assertEqual(notification.recipient, self.bob)

    def test_replying_to_your_own_post_does_not_notify(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("comment-create", args=[self.post.pk]), {"body": "talking to myself"})

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.REPLY).exists())

    def test_replying_to_your_own_comment_does_not_notify(self):
        top_level = Comment.objects.create(author=self.alice, post=self.post, body="first")
        self.client.force_login(self.alice)

        self.client.post(
            reverse("comment-create", args=[self.post.pk]),
            {"body": "replying to myself", "parent": top_level.pk},
        )

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.REPLY).exists())


class UpvoteNotificationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="hello")
        self.comment = Comment.objects.create(author=self.alice, post=self.post, body="a comment")

    def test_upvoting_a_post_notifies_its_author(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        notification = Notification.objects.get(kind=Notification.Kind.UPVOTE)
        self.assertEqual(notification.recipient, self.alice)
        self.assertEqual(notification.actor, self.bob)
        self.assertIsNone(notification.comment)

    def test_upvoting_a_comment_notifies_its_author(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-upvote", args=[self.comment.pk]))

        notification = Notification.objects.get(kind=Notification.Kind.UPVOTE)
        self.assertEqual(notification.recipient, self.alice)
        self.assertEqual(notification.comment, self.comment)

    def test_downvoting_never_notifies(self):
        self.client.force_login(self.bob)

        self.client.post(reverse("post-downvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())

    def test_removing_an_upvote_does_not_notify_again(self):
        self.client.force_login(self.bob)
        self.client.post(reverse("post-upvote", args=[self.post.pk]))
        Notification.objects.filter(kind=Notification.Kind.UPVOTE).delete()

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())

    def test_flipping_a_downvote_to_an_upvote_notifies(self):
        self.client.force_login(self.bob)
        self.client.post(reverse("post-downvote", args=[self.post.pk]))

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertTrue(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())

    def test_upvoting_your_own_post_does_not_notify(self):
        self.client.force_login(self.alice)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())


class MuteBlockNotificationSuppressionTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")

    def test_muting_suppresses_an_upvote_notification(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.bob)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())

    def test_blocking_suppresses_an_upvote_notification(self):
        Block.objects.create(blocker=self.alice, blocked=self.bob)
        self.client.force_login(self.bob)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())

    def test_muting_suppresses_a_reply_notification(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-create", args=[self.post.pk]), {"body": "a comment"})

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.REPLY).exists())

    def test_muting_suppresses_a_mention_notification(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.bob)

        self.client.post(reverse("post-create"), {"body": f"hi @{self.alice.username}"})

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.MENTION).exists())

    def test_unrelated_users_notifications_are_unaffected(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        carol = make_user("carol")
        self.client.force_login(carol)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertTrue(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())


class NotificationPreferenceTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.post = Post.objects.create(author=self.alice, body="a post")

    def test_disabling_upvote_notifications_suppresses_them(self):
        self.alice.profile.notify_on_upvotes = False
        self.alice.profile.save(update_fields=["notify_on_upvotes"])
        self.client.force_login(self.bob)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())

    def test_disabling_upvotes_does_not_suppress_replies(self):
        self.alice.profile.notify_on_upvotes = False
        self.alice.profile.save(update_fields=["notify_on_upvotes"])
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-create", args=[self.post.pk]), {"body": "a comment"})

        self.assertTrue(Notification.objects.filter(kind=Notification.Kind.REPLY).exists())

    def test_disabling_reply_notifications_suppresses_a_top_level_comment(self):
        self.alice.profile.notify_on_replies = False
        self.alice.profile.save(update_fields=["notify_on_replies"])
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-create", args=[self.post.pk]), {"body": "a comment"})

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.REPLY).exists())

    def test_disabling_reply_notifications_suppresses_a_nested_reply(self):
        comment = Comment.objects.create(author=self.alice, post=self.post, body="original")
        self.alice.profile.notify_on_replies = False
        self.alice.profile.save(update_fields=["notify_on_replies"])
        self.client.force_login(self.bob)

        self.client.post(
            reverse("comment-create", args=[self.post.pk]), {"body": "a reply", "parent": comment.pk}
        )

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.REPLY).exists())

    def test_disabling_mention_notifications_suppresses_a_mention_in_a_post(self):
        self.alice.profile.notify_on_mentions = False
        self.alice.profile.save(update_fields=["notify_on_mentions"])
        self.client.force_login(self.bob)

        self.client.post(reverse("post-create"), {"body": f"hi @{self.alice.username}"})

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.MENTION).exists())

    def test_disabling_mention_notifications_suppresses_a_mention_in_a_comment(self):
        self.alice.profile.notify_on_mentions = False
        self.alice.profile.save(update_fields=["notify_on_mentions"])
        self.client.force_login(self.bob)

        self.client.post(reverse("comment-create", args=[self.post.pk]), {"body": f"hi @{self.alice.username}"})

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.MENTION).exists())

    def test_preference_is_per_recipient(self):
        self.alice.profile.notify_on_upvotes = False
        self.alice.profile.save(update_fields=["notify_on_upvotes"])
        bobs_post = Post.objects.create(author=self.bob, body="bob's post")
        self.client.force_login(self.alice)

        self.client.post(reverse("post-upvote", args=[bobs_post.pk]))

        self.assertTrue(Notification.objects.filter(kind=Notification.Kind.UPVOTE, recipient=self.bob).exists())

    def test_muting_the_actor_still_suppresses_even_with_the_kind_enabled(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.bob)

        self.client.post(reverse("post-upvote", args=[self.post.pk]))

        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.UPVOTE).exists())


class SearchViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.matching_post = Post.objects.create(author=self.alice, body="a post about pelicans")
        self.other_post = Post.objects.create(author=self.alice, body="a post about seagulls")
        self.matching_comment = Comment.objects.create(
            author=self.bob, post=self.other_post, body="I saw a pelican yesterday"
        )
        self.other_comment = Comment.objects.create(author=self.bob, post=self.other_post, body="nice photo")

    def test_empty_query_shows_no_results(self):
        response = self.client.get(reverse("search"))
        self.assertNotIn("posts_preview", response.context)
        self.assertEqual(response.context["query"], "")

    def test_all_type_shows_matching_posts_and_comments(self):
        response = self.client.get(reverse("search"), {"q": "pelican"})
        self.assertEqual(list(response.context["posts_preview"]), [self.matching_post])
        self.assertEqual(list(response.context["comments_preview"]), [self.matching_comment])

    def test_search_is_case_insensitive(self):
        response = self.client.get(reverse("search"), {"q": "PELICAN"})
        self.assertEqual(list(response.context["posts_preview"]), [self.matching_post])

    def test_posts_only_type_excludes_comments(self):
        response = self.client.get(reverse("search"), {"q": "pelican", "type": "posts"})
        self.assertIn(self.matching_post, response.context["posts_page"])
        self.assertNotIn("comments_page", response.context)
        self.assertNotIn("comments_preview", response.context)

    def test_comments_only_type_excludes_posts(self):
        response = self.client.get(reverse("search"), {"q": "pelican", "type": "comments"})
        self.assertIn(self.matching_comment, response.context["comments_page"])
        self.assertNotIn("posts_page", response.context)
        self.assertNotIn("posts_preview", response.context)

    def test_invalid_type_falls_back_to_all(self):
        response = self.client.get(reverse("search"), {"q": "pelican", "type": "bogus"})
        self.assertEqual(response.context["search_type"], "all")

    def test_see_all_link_only_shown_past_the_preview_cap(self):
        for i in range(15):
            Post.objects.create(author=self.alice, body=f"pelican sighting {i}")

        response = self.client.get(reverse("search"), {"q": "pelican"})

        self.assertTrue(response.context["posts_has_more"])
        self.assertEqual(response.context["posts_total"], 16)
        self.assertEqual(len(response.context["posts_preview"]), 10)

    def test_muted_authors_content_excluded_for_the_searcher(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("search"), {"q": "pelican"})

        self.assertNotIn(self.matching_comment, response.context["comments_preview"])

    def test_muted_authors_content_still_shows_for_everyone_else(self):
        Mute.objects.create(muter=self.alice, muted=self.bob)
        carol = make_user("carol")
        self.client.force_login(carol)

        response = self.client.get(reverse("search"), {"q": "pelican"})

        self.assertIn(self.matching_comment, response.context["comments_preview"])

    def test_deleted_post_never_matches(self):
        self.matching_post.deleted = True
        self.matching_post.body = ""
        self.matching_post.save(update_fields=["deleted", "body"])

        response = self.client.get(reverse("search"), {"q": "pelican"})

        self.assertNotIn(self.matching_post, response.context["posts_preview"])

    def test_pagination_beyond_the_page_size(self):
        for i in range(10):
            Post.objects.create(author=self.alice, body=f"pelican sighting {i}")

        first_page = self.client.get(reverse("search"), {"q": "pelican", "type": "posts"})
        second_page = self.client.get(reverse("search"), {"q": "pelican", "type": "posts", "page": 2})

        self.assertTrue(first_page.context["posts_page"].has_next())
        self.assertEqual(len(second_page.context["posts_page"]), 5)

    def test_anonymous_can_search(self):
        response = self.client.get(reverse("search"), {"q": "pelican"})
        self.assertEqual(response.status_code, 200)
