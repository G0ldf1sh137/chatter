from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import BooleanField, Count, Exists, Max, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.models import Block, Mute, is_blocked_either_way, is_muted_or_blocked

from .forms import CommentEditForm, CommentForm, MessageForm, PostForm
from .hashtags import sync_post_tags
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
from .ranking import rank_posts


NOTIFICATION_PREFERENCE_FIELDS = {
    Notification.Kind.MENTION: "notify_on_mentions",
    Notification.Kind.REPLY: "notify_on_replies",
    Notification.Kind.UPVOTE: "notify_on_upvotes",
}


def notifications_enabled(recipient, kind):
    return getattr(recipient.profile, NOTIFICATION_PREFERENCE_FIELDS[kind])


def create_notification(kind, recipient, actor, post, comment=None):
    if recipient.pk == actor.pk:
        return
    if is_muted_or_blocked(recipient, actor):
        return
    if not notifications_enabled(recipient, kind):
        return
    Notification.objects.create(kind=kind, recipient=recipient, actor=actor, post=post, comment=comment)


def notify_mentioned_users(body, author, post, comment=None):
    Notification.objects.bulk_create(
        Notification(kind=Notification.Kind.MENTION, recipient=user, actor=author, post=post, comment=comment)
        for user in extract_mentioned_users(body, exclude=author)
        if not is_muted_or_blocked(user, author) and notifications_enabled(user, Notification.Kind.MENTION)
    )


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


def annotate_saved(queryset, user):
    if not user.is_authenticated:
        return queryset.annotate(is_saved=Value(False, output_field=BooleanField()))
    saved_qs = SavedPost.objects.filter(post=OuterRef("pk"), user=user)
    return queryset.annotate(is_saved=Exists(saved_qs))


def toggle_vote(vote_model, lookup, user, value):
    existing = vote_model.objects.filter(user=user, **lookup).first()
    if existing is None:
        vote_model.objects.create(user=user, value=value, **lookup)
        return "created"
    elif existing.value == value:
        existing.delete()
        return "removed"
    else:
        existing.value = value
        existing.save(update_fields=["value"])
        return "flipped"


def toggle_reaction(reaction_model, lookup, user, emoji):
    existing = reaction_model.objects.filter(user=user, **lookup).first()
    if existing is None:
        reaction_model.objects.create(user=user, emoji=emoji, **lookup)
    elif existing.emoji == emoji:
        existing.delete()
    else:
        existing.emoji = emoji
        existing.save(update_fields=["emoji"])


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

# How many of each type show in the combined "all" search view before
# pointing to the fully paginated single-type list instead.
SEARCH_PREVIEW_LIMIT = 10
SEARCH_TYPE_ALL = "all"
SEARCH_TYPE_POSTS = "posts"
SEARCH_TYPE_COMMENTS = "comments"
SEARCH_TYPES = {SEARCH_TYPE_ALL, SEARCH_TYPE_POSTS, SEARCH_TYPE_COMMENTS}

TAG_INDEX_PAGE_SIZE = 20
TAG_SEARCH_LIMIT = 8


def is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def hidden_author_ids(user):
    # Authors a viewer has muted or blocked - excluded from both the feed
    # and search results, so neither is a loophole around the other.
    if not user.is_authenticated:
        return []
    ids = list(Mute.objects.filter(muter=user).values_list("muted", flat=True))
    ids += list(Block.objects.filter(blocker=user).values_list("blocked", flat=True))
    return ids


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
        queryset = Post.objects.select_related("author", "author__profile").prefetch_related("reactions")
        hidden = hidden_author_ids(self.request.user)
        if hidden:
            queryset = queryset.exclude(author_id__in=hidden)
        queryset = annotate_votes(queryset, PostVote, "post", self.request.user)
        return annotate_saved(queryset, self.request.user)

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


class SearchView(TemplateView):
    template_name = "posts/search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        search_type = self.request.GET.get("type", SEARCH_TYPE_ALL)
        if search_type not in SEARCH_TYPES:
            search_type = SEARCH_TYPE_ALL
        context["query"] = query
        context["search_type"] = search_type
        if not query:
            return context

        hidden = hidden_author_ids(self.request.user)

        posts = Post.objects.filter(body__icontains=query, deleted=False).select_related(
            "author", "author__profile"
        ).prefetch_related("reactions")
        comments = Comment.objects.filter(body__icontains=query, deleted=False).select_related(
            "author", "author__profile", "post"
        )
        if hidden:
            posts = posts.exclude(author_id__in=hidden)
            comments = comments.exclude(author_id__in=hidden)
        posts = annotate_votes(posts.order_by("-created_at"), PostVote, "post", self.request.user)
        posts = annotate_saved(posts, self.request.user)
        comments = annotate_votes(comments.order_by("-created_at"), CommentVote, "comment", self.request.user)

        if search_type == SEARCH_TYPE_POSTS:
            context["posts_page"] = Paginator(posts, POSTS_PAGE_SIZE).get_page(self.request.GET.get("page"))
        elif search_type == SEARCH_TYPE_COMMENTS:
            context["comments_page"] = Paginator(comments, COMMENTS_PAGE_SIZE).get_page(self.request.GET.get("page"))
        else:
            posts_total = posts.count()
            comments_total = comments.count()
            context["posts_preview"] = posts[:SEARCH_PREVIEW_LIMIT]
            context["posts_total"] = posts_total
            context["posts_has_more"] = posts_total > SEARCH_PREVIEW_LIMIT
            context["comments_preview"] = comments[:SEARCH_PREVIEW_LIMIT]
            context["comments_total"] = comments_total
            context["comments_has_more"] = comments_total > SEARCH_PREVIEW_LIMIT
        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = "posts/post_form.html"

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)
        sync_post_tags(self.object, self.object.body)
        notify_mentioned_users(self.object.body, self.object.author, self.object)
        return response


class PostDetailView(DetailView):
    model = Post
    template_name = "posts/post_detail.html"
    context_object_name = "post"

    def get_queryset(self):
        queryset = Post.objects.select_related("author", "author__profile").prefetch_related("reactions")
        queryset = annotate_votes(queryset, PostVote, "post", self.request.user)
        return annotate_saved(queryset, self.request.user)

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
        post = self.get_object()
        return post.author_id == self.request.user.id and not post.deleted

    def form_valid(self, form):
        if form.has_changed():
            form.instance.edited = True
        response = super().form_valid(form)
        sync_post_tags(self.object, self.object.body)
        return response


class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    def get_object(self):
        return get_object_or_404(Post, pk=self.kwargs["pk"])

    def test_func(self):
        return self.get_object().author_id == self.request.user.id

    def post(self, request, pk):
        post = self.get_object()
        post.body = ""
        post.deleted = True
        if post.image:
            post.image.delete(save=False)
        post.save(update_fields=["body", "deleted", "image"])
        return redirect(post.get_absolute_url())


class PostSaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        SavedPost.objects.get_or_create(user=request.user, post=post)
        return redirect_back(request, post.get_absolute_url())


class PostUnsaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        SavedPost.objects.filter(user=request.user, post=post).delete()
        return redirect_back(request, post.get_absolute_url())


class SavedPostsView(LoginRequiredMixin, ListView):
    model = Post
    template_name = "posts/saved_posts.html"
    context_object_name = "posts"
    paginate_by = POSTS_PAGE_SIZE

    def get_queryset(self):
        queryset = Post.objects.filter(saved_by__user=self.request.user).select_related(
            "author", "author__profile"
        ).prefetch_related("reactions")
        queryset = queryset.order_by("-saved_by__created_at")
        queryset = annotate_votes(queryset, PostVote, "post", self.request.user)
        return annotate_saved(queryset, self.request.user)

    def render_to_response(self, context, **response_kwargs):
        if not is_ajax(self.request):
            return super().render_to_response(context, **response_kwargs)

        html = render_to_string("posts/_post_list.html", {"posts": context["posts"]}, request=self.request)
        next_url = None
        page_obj = context.get("page_obj")
        if page_obj and page_obj.has_next():
            next_url = f"{self.request.path}?page={page_obj.next_page_number()}"
        return JsonResponse({"html": html, "next_url": next_url})


class TagSearchView(LoginRequiredMixin, View):
    # Powers the #hashtag autocomplete in post/comment textareas
    # (posts/static/posts/js/autocomplete.js) - mirrors UserSearchView
    # (accounts/views.py) exactly, just against Tag.name instead of username.
    def get(self, request):
        query = request.GET.get("q", "").strip().lower()
        if not query:
            return JsonResponse({"names": []})
        names = list(
            Tag.objects.filter(name__istartswith=query).order_by("name").values_list("name", flat=True)[
                :TAG_SEARCH_LIMIT
            ]
        )
        return JsonResponse({"names": names})


class TagIndexView(ListView):
    model = Tag
    template_name = "posts/tag_index.html"
    context_object_name = "tags"
    paginate_by = TAG_INDEX_PAGE_SIZE

    def get_queryset(self):
        return (
            Tag.objects.annotate(post_count=Count("posts", filter=Q(posts__deleted=False)))
            .filter(post_count__gt=0)
            .order_by("-post_count", "name")
        )


class TagDetailView(ListView):
    model = Post
    template_name = "posts/tag_detail.html"
    context_object_name = "posts"
    paginate_by = POSTS_PAGE_SIZE

    def get_queryset(self):
        self.tag_name = self.kwargs["name"].lower()
        queryset = Post.objects.filter(tags__name=self.tag_name, deleted=False).select_related(
            "author", "author__profile"
        ).prefetch_related("reactions")
        hidden = hidden_author_ids(self.request.user)
        if hidden:
            queryset = queryset.exclude(author_id__in=hidden)
        queryset = annotate_votes(queryset.order_by("-created_at"), PostVote, "post", self.request.user)
        return annotate_saved(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tag_name"] = self.tag_name
        return context

    def render_to_response(self, context, **response_kwargs):
        if not is_ajax(self.request):
            return super().render_to_response(context, **response_kwargs)

        html = render_to_string("posts/_post_list.html", {"posts": context["posts"]}, request=self.request)
        next_url = None
        page_obj = context.get("page_obj")
        if page_obj and page_obj.has_next():
            next_url = f"{self.request.path}?page={page_obj.next_page_number()}"
        return JsonResponse({"html": html, "next_url": next_url})


class PostReportView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        if post.author_id != request.user.id:
            Report.objects.get_or_create(
                reporter=request.user,
                post=post,
                comment=None,
                defaults={"reason": request.POST.get("reason", "").strip()},
            )
        return redirect_back(request, post.get_absolute_url())


class CommentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        form = CommentForm(request.POST)
        if form.is_valid():
            parent = None
            parent_id = form.cleaned_data.get("parent")
            if parent_id:
                parent = get_object_or_404(Comment, pk=parent_id, post=post)
            comment = Comment.objects.create(
                author=request.user,
                post=post,
                parent=parent,
                body=form.cleaned_data["body"],
            )
            reply_recipient = parent.author if parent else post.author
            create_notification(Notification.Kind.REPLY, reply_recipient, comment.author, post, comment=comment)
            notify_mentioned_users(comment.body, comment.author, post, comment=comment)
        return redirect("post-detail", pk=post.pk)


class CommentEditView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        if comment.author_id != request.user.id or comment.deleted:
            raise Http404

        form = CommentEditForm(request.POST, instance=comment)
        if form.is_valid():
            if form.has_changed():
                form.instance.edited = True
            form.save()
        return redirect(f"{comment.post.get_absolute_url()}#comment-{comment.pk}")


class CommentDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        if comment.author_id != request.user.id:
            raise Http404
        comment.body = ""
        comment.deleted = True
        comment.save(update_fields=["body", "deleted"])
        return redirect(f"{comment.post.get_absolute_url()}#comment-{comment.pk}")


class CommentReportView(LoginRequiredMixin, View):
    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        if comment.author_id != request.user.id:
            Report.objects.get_or_create(
                reporter=request.user,
                post=comment.post,
                comment=comment,
                defaults={"reason": request.POST.get("reason", "").strip()},
            )
        return redirect_back(request, f"{comment.post.get_absolute_url()}#comment-{comment.pk}")


class PostVoteView(LoginRequiredMixin, View):
    value = None

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        action = toggle_vote(PostVote, {"post": post}, request.user, self.value)
        if self.value == PostVote.UP and action in ("created", "flipped"):
            create_notification(Notification.Kind.UPVOTE, post.author, request.user, post)
        return redirect_back(request, post.get_absolute_url())


class PostReactionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        emoji = request.POST.get("emoji")
        if emoji in PostReaction.Emoji.values:
            toggle_reaction(PostReaction, {"post": post}, request.user, emoji)
        return redirect_back(request, post.get_absolute_url())


class CommentVoteView(LoginRequiredMixin, View):
    value = None

    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        action = toggle_vote(CommentVote, {"comment": comment}, request.user, self.value)
        if self.value == CommentVote.UP and action in ("created", "flipped"):
            create_notification(Notification.Kind.UPVOTE, comment.author, request.user, comment.post, comment=comment)
        return redirect_back(request, comment.post.get_absolute_url())


def get_or_create_conversation(user_a, user_b):
    # Always stored lo/hi by pk (see Conversation.Meta.constraints) so a
    # conversation started from either side's profile page resolves to the
    # same row instead of creating a mirrored duplicate.
    lo, hi = sorted([user_a, user_b], key=lambda u: u.pk)
    conversation, _ = Conversation.objects.get_or_create(user1=lo, user2=hi)
    return conversation


def unread_message_count(user):
    return (
        Message.objects.filter(Q(conversation__user1=user) | Q(conversation__user2=user))
        .exclude(sender=user)
        .filter(read=False)
        .count()
    )


class StartConversationView(LoginRequiredMixin, View):
    def post(self, request, username):
        other = get_object_or_404(User, username=username)
        if other == request.user:
            messages.error(request, "You can't message yourself.")
            return redirect("profile", username=username)
        if is_blocked_either_way(request.user, other):
            messages.error(request, "You can't message this user.")
            return redirect("profile", username=username)
        conversation = get_or_create_conversation(request.user, other)
        return redirect("conversation-detail", pk=conversation.pk)


class ConversationListView(LoginRequiredMixin, TemplateView):
    template_name = "posts/conversation_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        conversations = list(
            Conversation.objects.filter(Q(user1=user) | Q(user2=user))
            .select_related("user1", "user2")
            .annotate(
                last_message_at=Max("messages__created_at"),
                unread_count=Count("messages", filter=Q(messages__read=False) & ~Q(messages__sender=user)),
            )
            .order_by("-last_message_at")
        )
        for conversation in conversations:
            conversation.other = conversation.other_participant(user)
        context["conversations"] = conversations
        return context


class ConversationDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Conversation
    template_name = "posts/conversation_detail.html"
    context_object_name = "conversation"

    def test_func(self):
        conversation = self.get_object()
        return self.request.user.id in (conversation.user1_id, conversation.user2_id)

    def get_queryset(self):
        return Conversation.objects.select_related("user1", "user2")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Marked read before rendering, not after, so the header's unread
        # badge (via the context processor) reflects this same response's
        # updated count instead of the stale pre-read one.
        self.object.messages.filter(read=False).exclude(sender=request.user).update(read=True)
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["other"] = self.object.other_participant(self.request.user)
        context["message_list"] = self.object.messages.select_related("sender")
        context["message_form"] = MessageForm()
        return context


class MessageSendView(LoginRequiredMixin, View):
    def post(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk)
        if request.user.id not in (conversation.user1_id, conversation.user2_id):
            raise Http404

        other = conversation.other_participant(request.user)
        if is_blocked_either_way(request.user, other):
            messages.error(request, "You can't message this user.")
            return redirect("conversation-detail", pk=conversation.pk)

        form = MessageForm(request.POST, request.FILES)
        if form.is_valid():
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                body=form.cleaned_data["body"],
                image=form.cleaned_data["image"],
            )
        return redirect("conversation-detail", pk=conversation.pk)


class UnreadMessageCountView(LoginRequiredMixin, View):
    def get(self, request):
        return JsonResponse({"count": unread_message_count(request.user)})


def unread_notification_count(user):
    return Notification.objects.filter(recipient=user, read=False).count()


class NotificationListView(LoginRequiredMixin, TemplateView):
    template_name = "posts/notification_list.html"

    def get(self, request, *args, **kwargs):
        # Marked read before rendering, not after, for the same reason
        # ConversationDetailView does: the header badge (via the context
        # processor) should reflect this response's own updated count.
        Notification.objects.filter(recipient=request.user, read=False).update(read=True)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notifications"] = Notification.objects.filter(
            recipient=self.request.user, dismissed=False
        ).select_related("actor", "post", "comment")
        return context


class NotificationDismissView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.dismissed = True
        notification.save(update_fields=["dismissed"])
        return redirect("notification-list")


class NotificationDismissAllView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(recipient=request.user, dismissed=False).update(dismissed=True)
        return redirect("notification-list")


class UnreadNotificationCountView(LoginRequiredMixin, View):
    def get(self, request):
        return JsonResponse({"count": unread_notification_count(request.user)})
