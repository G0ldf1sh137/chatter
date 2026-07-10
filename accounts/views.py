from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, TemplateView, UpdateView

from games import stats as game_stats
from games.models import Match
from posts.models import CommentVote, PostVote
from posts.views import annotate_votes

from .emails import send_verification_email
from .forms import ProfileForm, RegistrationForm, ResendVerificationForm, UserProfileForm
from .models import Follow, Profile
from .tokens import TokenExpired, TokenInvalid, verify_token

PROFILE_ITEM_LIMIT = 20


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("verification-sent")

    def form_valid(self, form):
        response = super().form_valid(form)
        send_verification_email(self.request, self.object)
        self.request.session["pending_verification_email"] = self.object.email
        return response


class VerificationSentView(TemplateView):
    template_name = "accounts/verification_sent.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["email"] = self.request.session.get("pending_verification_email")
        return context


class VerifyEmailView(View):
    def get(self, request, token):
        try:
            user_id = verify_token(token, max_age=settings.EMAIL_VERIFICATION_MAX_AGE)
        except TokenExpired:
            return render(request, "accounts/verification_failed.html", {"reason": "expired"})
        except TokenInvalid:
            return render(request, "accounts/verification_failed.html", {"reason": "invalid"})

        user = get_object_or_404(User, pk=user_id)
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Your email is verified — welcome to Chatter!")
        return redirect("feed")


class ResendVerificationView(FormView):
    form_class = ResendVerificationForm
    template_name = "accounts/resend_verification.html"
    success_url = reverse_lazy("verification-sent")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        user = User.objects.filter(email=email, profile__email_verified=False).first()
        if user:
            send_verification_email(self.request, user)
        self.request.session["pending_verification_email"] = email
        return super().form_valid(form)


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

        ttt_wins, ttt_losses, ttt_draws = game_stats.match_record(profile_user, Match.Game.TIC_TAC_TOE)
        context["ttt_record"] = {"wins": ttt_wins, "losses": ttt_losses, "draws": ttt_draws}
        rps_wins, rps_losses, rps_draws = game_stats.match_record(profile_user, Match.Game.ROCK_PAPER_SCISSORS)
        context["rps_record"] = {"wins": rps_wins, "losses": rps_losses, "draws": rps_draws}
        c4_wins, c4_losses, c4_draws = game_stats.match_record(profile_user, Match.Game.CONNECT_FOUR)
        context["connect4_record"] = {"wins": c4_wins, "losses": c4_losses, "draws": c4_draws}
        chk_wins, chk_losses, chk_draws = game_stats.match_record(profile_user, Match.Game.CHECKERS)
        context["checkers_record"] = {"wins": chk_wins, "losses": chk_losses, "draws": chk_draws}
        oth_wins, oth_losses, oth_draws = game_stats.match_record(profile_user, Match.Game.OTHELLO)
        context["othello_record"] = {"wins": oth_wins, "losses": oth_losses, "draws": oth_draws}
        nim_wins, nim_losses, nim_draws = game_stats.match_record(profile_user, Match.Game.NIM)
        context["nim_record"] = {"wins": nim_wins, "losses": nim_losses, "draws": nim_draws}
        bs_wins, bs_losses, bs_draws = game_stats.match_record(profile_user, Match.Game.BATTLESHIP)
        context["battleship_record"] = {"wins": bs_wins, "losses": bs_losses, "draws": bs_draws}
        str_wins, str_losses, str_draws = game_stats.match_record(profile_user, Match.Game.STRATEGO)
        context["stratego_record"] = {"wins": str_wins, "losses": str_losses, "draws": str_draws}
        mor_wins, mor_losses, mor_draws = game_stats.match_record(profile_user, Match.Game.NINE_MENS_MORRIS)
        context["morris_record"] = {"wins": mor_wins, "losses": mor_losses, "draws": mor_draws}
        bg_wins, bg_losses, bg_draws = game_stats.match_record(profile_user, Match.Game.BACKGAMMON)
        context["backgammon_record"] = {"wins": bg_wins, "losses": bg_losses, "draws": bg_draws}
        context["hangman_wins"] = game_stats.hangman_wins(profile_user)
        context["high_score_2048"] = game_stats.high_score_2048(profile_user)
        context["snake_high_score"] = game_stats.snake_high_score(profile_user)
        context["doodle_high_score"] = game_stats.doodle_high_score(profile_user)
        context["wordle_high_score"] = game_stats.wordle_high_score(profile_user)
        context["mastermind_high_score"] = game_stats.mastermind_high_score(profile_user)
        context["flappy_high_score"] = game_stats.flappy_high_score(profile_user)
        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile_edit.html"

    def get_object(self, queryset=None):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get_user_form(self, data=None):
        # A separate copy, not self.request.user itself - ModelForm validation
        # writes submitted values onto the bound instance before uniqueness
        # checks run, even when they ultimately fail. Binding request.user
        # directly would leak a rejected, unsaved username onto the same
        # object base.html's header reads for the nav link, pointing it at
        # someone else's profile for the rest of this response.
        user_copy = User.objects.get(pk=self.request.user.pk)
        return UserProfileForm(data=data, instance=user_copy)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("user_form", self.get_user_form())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        user_form = self.get_user_form(data=request.POST)
        if form.is_valid() and user_form.is_valid():
            saved_user = user_form.save()
            form.save()
            return redirect(reverse("profile", kwargs={"username": saved_user.username}))
        return self.render_to_response(self.get_context_data(form=form, user_form=user_form))


class PasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("profile-edit")

    def get_form_class(self):
        # Google-only signups have no usable password (allauth sets one
        # unusable at signup) - SetPasswordForm skips the old-password check
        # that PasswordChangeForm would otherwise always fail for them.
        return PasswordChangeForm if self.request.user.has_usable_password() else SetPasswordForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_password"] = self.request.user.has_usable_password()
        return context

    def form_valid(self, form):
        form.save()
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Your password has been updated.")
        return super().form_valid(form)


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
