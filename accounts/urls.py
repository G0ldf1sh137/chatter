from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("users/<str:username>/", views.ProfileView.as_view(), name="profile"),
    path("users/<str:username>/follow/", views.FollowView.as_view(), name="follow"),
    path("users/<str:username>/unfollow/", views.UnfollowView.as_view(), name="unfollow"),
]
