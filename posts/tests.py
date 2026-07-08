from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .markdown import render_markdown
from .models import Comment, Post
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

    def test_feed_orders_posts_newest_first(self):
        user = make_user("alice")
        first = Post.objects.create(author=user, body="first")
        second = Post.objects.create(author=user, body="second")
        response = self.client.get(reverse("feed"))
        self.assertEqual(list(response.context["posts"]), [second, first])

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
