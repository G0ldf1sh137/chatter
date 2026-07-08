from django.urls import path

from . import views

urlpatterns = [
    path("", views.FeedView.as_view(), name="feed"),
    path("posts/new/", views.PostCreateView.as_view(), name="post-create"),
    path("posts/<int:pk>/", views.PostDetailView.as_view(), name="post-detail"),
    path("posts/<int:pk>/edit/", views.PostEditView.as_view(), name="post-edit"),
    path("posts/<int:pk>/comment/", views.CommentCreateView.as_view(), name="comment-create"),
]
