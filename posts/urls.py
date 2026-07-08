from django.urls import path

from . import views
from .models import CommentVote, PostVote

urlpatterns = [
    path("", views.FeedView.as_view(), name="feed"),
    path("following/", views.FollowingFeedView.as_view(), name="following-feed"),
    path("posts/new/", views.PostCreateView.as_view(), name="post-create"),
    path("posts/<int:pk>/", views.PostDetailView.as_view(), name="post-detail"),
    path("posts/<int:pk>/edit/", views.PostEditView.as_view(), name="post-edit"),
    path("posts/<int:pk>/comment/", views.CommentCreateView.as_view(), name="comment-create"),
    path(
        "posts/<int:pk>/upvote/",
        views.PostVoteView.as_view(value=PostVote.UP),
        name="post-upvote",
    ),
    path(
        "posts/<int:pk>/downvote/",
        views.PostVoteView.as_view(value=PostVote.DOWN),
        name="post-downvote",
    ),
    path(
        "comments/<int:pk>/upvote/",
        views.CommentVoteView.as_view(value=CommentVote.UP),
        name="comment-upvote",
    ),
    path(
        "comments/<int:pk>/downvote/",
        views.CommentVoteView.as_view(value=CommentVote.DOWN),
        name="comment-downvote",
    ),
]
