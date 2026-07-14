from django.urls import path

from . import views
from .models import CommentVote, PostVote

urlpatterns = [
    path("", views.FeedView.as_view(), name="feed"),
    path("following/", views.FollowingFeedView.as_view(), name="following-feed"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("posts/new/", views.PostCreateView.as_view(), name="post-create"),
    path("posts/<uuid:pk>/", views.PostDetailView.as_view(), name="post-detail"),
    path("posts/<uuid:pk>/edit/", views.PostEditView.as_view(), name="post-edit"),
    path("posts/<uuid:pk>/delete/", views.PostDeleteView.as_view(), name="post-delete"),
    path("posts/<uuid:pk>/save/", views.PostSaveView.as_view(), name="post-save"),
    path("posts/<uuid:pk>/unsave/", views.PostUnsaveView.as_view(), name="post-unsave"),
    path("saved/", views.SavedPostsView.as_view(), name="saved-posts"),
    path("tags/<str:name>/", views.TagDetailView.as_view(), name="tag-detail"),
    path("posts/<uuid:pk>/report/", views.PostReportView.as_view(), name="post-report"),
    path("posts/<uuid:pk>/comment/", views.CommentCreateView.as_view(), name="comment-create"),
    path("comments/<uuid:pk>/edit/", views.CommentEditView.as_view(), name="comment-edit"),
    path("comments/<uuid:pk>/delete/", views.CommentDeleteView.as_view(), name="comment-delete"),
    path("comments/<uuid:pk>/report/", views.CommentReportView.as_view(), name="comment-report"),
    path(
        "posts/<uuid:pk>/upvote/",
        views.PostVoteView.as_view(value=PostVote.UP),
        name="post-upvote",
    ),
    path(
        "posts/<uuid:pk>/downvote/",
        views.PostVoteView.as_view(value=PostVote.DOWN),
        name="post-downvote",
    ),
    path(
        "comments/<uuid:pk>/upvote/",
        views.CommentVoteView.as_view(value=CommentVote.UP),
        name="comment-upvote",
    ),
    path(
        "comments/<uuid:pk>/downvote/",
        views.CommentVoteView.as_view(value=CommentVote.DOWN),
        name="comment-downvote",
    ),
    path("messages/", views.ConversationListView.as_view(), name="conversation-list"),
    path("messages/unread-count/", views.UnreadMessageCountView.as_view(), name="unread-message-count"),
    path("messages/start/<str:username>/", views.StartConversationView.as_view(), name="conversation-start"),
    path("messages/<uuid:pk>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("messages/<uuid:pk>/send/", views.MessageSendView.as_view(), name="message-send"),
    path("notifications/", views.NotificationListView.as_view(), name="notification-list"),
    path(
        "notifications/unread-count/",
        views.UnreadNotificationCountView.as_view(),
        name="unread-notification-count",
    ),
    path(
        "notifications/dismiss-all/",
        views.NotificationDismissAllView.as_view(),
        name="notification-dismiss-all",
    ),
    path(
        "notifications/<uuid:pk>/dismiss/",
        views.NotificationDismissView.as_view(),
        name="notification-dismiss",
    ),
]
