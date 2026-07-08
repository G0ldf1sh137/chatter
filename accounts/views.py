from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, UpdateView

from posts.models import CommentVote, PostVote
from posts.views import annotate_votes

from .forms import ProfileForm, RegistrationForm
from .models import Follow, Profile

PROFILE_ITEM_LIMIT = 20


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("feed")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        return response


class ProfileView(DetailView):
    model = User
    slug_field = "username"
    slug_url_kwarg = "username"
    context_object_name = "profile_user"
    template_name = "accounts/profile.html"

    def get_object(self, queryset=None):
        return User.objects.get(username=self.kwargs["username"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile_user = context["profile_user"]
        context["profile"], _ = Profile.objects.get_or_create(user=profile_user)
        posts = annotate_votes(profile_user.posts.all(), PostVote, "post", self.request.user)
        context["posts"] = posts[:PROFILE_ITEM_LIMIT]
        context["post_count"] = profile_user.posts.count()
        comments = profile_user.comments.select_related("post").order_by("-created_at")
        comments = annotate_votes(comments, CommentVote, "comment", self.request.user)
        context["comments"] = comments[:PROFILE_ITEM_LIMIT]
        context["comment_count"] = profile_user.comments.count()
        context["followers_count"] = profile_user.followers.count()
        context["following_count"] = profile_user.following.count()
        post_karma = PostVote.objects.filter(post__author=profile_user).aggregate(total=Sum("value"))["total"] or 0
        comment_karma = (
            CommentVote.objects.filter(comment__author=profile_user).aggregate(total=Sum("value"))["total"] or 0
        )
        context["karma"] = post_karma + comment_karma
        if self.request.user.is_authenticated:
            context["is_following"] = Follow.objects.filter(
                follower=self.request.user, followed=profile_user
            ).exists()
        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile_edit.html"

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get_success_url(self):
        return reverse("profile", kwargs={"username": self.request.user.username})


class FollowView(LoginRequiredMixin, View):
    def post(self, request, username):
        target = get_object_or_404(User, username=username)
        if target != request.user:
            Follow.objects.get_or_create(follower=request.user, followed=target)
        return redirect("profile", username=username)


class UnfollowView(LoginRequiredMixin, View):
    def post(self, request, username):
        target = get_object_or_404(User, username=username)
        Follow.objects.filter(follower=request.user, followed=target).delete()
        return redirect("profile", username=username)
