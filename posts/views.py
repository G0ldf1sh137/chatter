from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CommentForm, PostForm
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


class FeedView(ListView):
    model = Post
    template_name = "posts/feed.html"
    context_object_name = "posts"
    paginate_by = 20
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        comments = self.object.comments.select_related("author", "author__profile")
        comments = annotate_votes(comments, CommentVote, "comment", self.request.user)
        context["comment_tree"] = build_comment_tree(list(comments))
        context["comment_form"] = CommentForm()
        return context


class PostEditView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = "posts/post_form.html"

    def test_func(self):
        return self.get_object().author_id == self.request.user.id


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
