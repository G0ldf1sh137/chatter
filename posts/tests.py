from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Follow

from .markdown import render_markdown
from .models import Comment, CommentVote, Post, PostVote
from .views import build_comment_tree


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
