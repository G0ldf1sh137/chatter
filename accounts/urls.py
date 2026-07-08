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
    path("users/<str:username>/", views.ProfileView.as_view(), name="profile"),
    path("users/<str:username>/follow/", views.FollowView.as_view(), name="follow"),
    path("users/<str:username>/unfollow/", views.UnfollowView.as_view(), name="unfollow"),
]
