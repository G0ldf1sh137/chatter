from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CommentEditForm, CommentForm, PostForm
from .models import Comment, CommentVote, Post, PostVote
from .ranking import rank_posts


def build_comment_tree(comments):
    by_parent = defaultdict(list)
    for comment in comments:
        by_parent[comment.parent_id].append(comment)

    def attach_children(nodes):
        for node in nodes:
            node.children = by_parent.get(node.id, [])
            attach_children(node.children)

    top_level = by_parent.get(None, [])
    attach_children(top_level)
    return top_level


def annotate_votes(queryset, vote_model, fk_name, user):
    # Aggregation via annotate() silently drops ordering (explicit or the model's
    # default Meta.ordering) from the generated SQL, so it must be reapplied after.
    ordering = queryset.query.order_by or queryset.model._meta.ordering
    queryset = queryset.annotate(score=Coalesce(Sum("votes__value"), 0))
    if user.is_authenticated:
        user_vote_qs = vote_model.objects.filter(**{fk_name: OuterRef("pk")}, user=user).values("value")[:1]
        queryset = queryset.annotate(user_vote=Subquery(user_vote_qs))
    if ordering:
        queryset = queryset.order_by(*ordering)
    return queryset


def toggle_vote(vote_model, lookup, user, value):
    existing = vote_model.objects.filter(user=user, **lookup).first()
    if existing is None:
        vote_model.objects.create(user=user, value=value, **lookup)
    elif existing.value == value:
        existing.delete()
    else:
        existing.value = value
        existing.save(update_fields=["value"])


def redirect_back(request, fallback):
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        return redirect(referer)
    return redirect(fallback)


SORT_DEFAULT = "default"
SORT_TOP = "top"
SORT_NEW = "new"
SORT_CHOICES = {SORT_DEFAULT, SORT_TOP, SORT_NEW}

# Initial page size for both the feed and a post's top-level comments -
# infinite_scroll.js requests further pages as the user scrolls near the
# bottom, rather than loading everything (or a manual pager) upfront.
POSTS_PAGE_SIZE = 6
COMMENTS_PAGE_SIZE = 6


def is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


class FeedView(ListView):
    model = Post
    template_name = "posts/feed.html"
    context_object_name = "posts"
    paginate_by = POSTS_PAGE_SIZE
    active_feed = "all"

    def get_sort(self):
        sort = self.request.GET.get("sort", SORT_DEFAULT)
        return sort if sort in SORT_CHOICES else SORT_DEFAULT

    def get_base_queryset(self):
        queryset = Post.objects.select_related("author", "author__profile")
        return annotate_votes(queryset, PostVote, "post", self.request.user)

    def get_queryset(self):
        queryset = self.get_base_queryset()
        sort = self.get_sort()
        if sort == SORT_TOP:
            return queryset.order_by("-score", "-created_at")
        if sort == SORT_NEW:
            return queryset.order_by("-created_at")
        return rank_posts(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_feed"] = self.active_feed
        context["active_sort"] = self.get_sort()
        return context

    def render_to_response(self, context, **response_kwargs):
        if not is_ajax(self.request):
            return super().render_to_response(context, **response_kwargs)

        html = render_to_string("posts/_post_list.html", {"posts": context["posts"]}, request=self.request)
        next_url = None
        page_obj = context.get("page_obj")
        if page_obj and page_obj.has_next():
            next_url = f"{self.request.path}?page={page_obj.next_page_number()}&sort={self.get_sort()}"
        return JsonResponse({"html": html, "next_url": next_url})


class FollowingFeedView(LoginRequiredMixin, FeedView):
    active_feed = "following"

    def get_base_queryset(self):
        return super().get_base_queryset().filter(author__followers__follower=self.request.user)


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = "posts/post_form.html"

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)


class PostDetailView(DetailView):
    model = Post
    template_name = "posts/post_detail.html"
    context_object_name = "post"

    def get_queryset(self):
        queryset = Post.objects.select_related("author", "author__profile")
        return annotate_votes(queryset, PostVote, "post", self.request.user)

    def get_comment_tree(self):
        comments = self.object.comments.select_related("author", "author__profile")
        comments = annotate_votes(comments, CommentVote, "comment", self.request.user)
        return build_comment_tree(list(comments))

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if is_ajax(request):
            return self.render_comments_page()
        return self.render_to_response(self.get_context_data(object=self.object))

    def render_comments_page(self):
        # Paginates over the already-built tree in Python rather than the
        # underlying queryset: a top-level comment's replies must stay with
        # it regardless of thread depth, and this app's comment trees are
        # small enough that rebuilding the full tree per page is proportionate
        # (annotate_votes already re-runs on every load for the same reason).
        try:
            page = int(self.request.GET.get("page", 1))
        except ValueError:
            page = 1
        tree = self.get_comment_tree()
        start = (page - 1) * COMMENTS_PAGE_SIZE
        end = start + COMMENTS_PAGE_SIZE
        html = render_to_string(
            "posts/_comment_list.html", {"comment_tree": tree[start:end]}, request=self.request
        )
        next_url = None
        if end < len(tree):
            next_url = f"{self.object.get_absolute_url()}?page={page + 1}"
        return JsonResponse({"html": html, "next_url": next_url})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = self.get_comment_tree()
        context["comment_tree"] = tree[:COMMENTS_PAGE_SIZE]
        context["comments_has_next"] = len(tree) > COMMENTS_PAGE_SIZE
        context["comment_form"] = CommentForm()
        return context


class PostEditView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = "posts/post_form.html"

    def test_func(self):
        return self.get_object().author_id == self.request.user.id

    def form_valid(self, form):
        if form.has_changed():
            form.instance.edited = True
        return super().form_valid(form)


class CommentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        form = CommentForm(request.POST)
        if form.is_valid():
            parent = None
            parent_id = form.cleaned_data.get("parent")
            if parent_id:
                parent = get_object_or_404(Comment, pk=parent_id, post=post)
            Comment.objects.create(
                author=request.user,
                post=post,
                parent=parent,
                body=form.cleaned_data["body"],
            )
        return redirect("post-detail", pk=post.pk)


class CommentEditView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        if comment.author_id != request.user.id:
            raise Http404

        form = CommentEditForm(request.POST, instance=comment)
        if form.is_valid():
            if form.has_changed():
                form.instance.edited = True
            form.save()
        return redirect(f"{comment.post.get_absolute_url()}#comment-{comment.pk}")


class PostVoteView(LoginRequiredMixin, View):
    value = None

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        toggle_vote(PostVote, {"post": post}, request.user, self.value)
        return redirect_back(request, post.get_absolute_url())


class CommentVoteView(LoginRequiredMixin, View):
    value = None

    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        toggle_vote(CommentVote, {"comment": comment}, request.user, self.value)
        return redirect_back(request, comment.post.get_absolute_url())
