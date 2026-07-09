from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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
