from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EmailVerifiedAuthenticationForm

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html", form_class=EmailVerifiedAuthenticationForm),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("verification-sent/", views.VerificationSentView.as_view(), name="verification-sent"),
    path("verify-email/<str:token>/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", views.ResendVerificationView.as_view(), name="resend-verification"),
    path("settings/profile/", views.ProfileEditView.as_view(), name="profile-edit"),
    path("settings/password/", views.PasswordChangeView.as_view(), name="password-change"),
    path("users/search/", views.UserSearchView.as_view(), name="user-search"),
    path("users/<str:username>/", views.ProfileView.as_view(), name="profile"),
    path("users/<str:username>/followers/", views.UserListView.as_view(kind="followers"), name="followers-list"),
    path("users/<str:username>/following/", views.UserListView.as_view(kind="following"), name="following-list"),
    path("users/<str:username>/follow/", views.FollowView.as_view(), name="follow"),
    path("users/<str:username>/unfollow/", views.UnfollowView.as_view(), name="unfollow"),
    path("users/<str:username>/mute/", views.MuteView.as_view(), name="mute"),
    path("users/<str:username>/unmute/", views.UnmuteView.as_view(), name="unmute"),
    path("users/<str:username>/block/", views.BlockView.as_view(), name="block"),
    path("users/<str:username>/unblock/", views.UnblockView.as_view(), name="unblock"),
    path("users/<str:username>/suspend/", views.SuspendUserView.as_view(), name="suspend-user"),
    path("users/<str:username>/unsuspend/", views.UnsuspendUserView.as_view(), name="unsuspend-user"),
]
