from django.urls import path

from . import views

urlpatterns = [
    path("", views.GamesHubView.as_view(), name="games-hub"),
    path("ttt/challenge/<str:username>/", views.TicTacToeChallengeView.as_view(), name="ttt-challenge"),
    path("ttt/<int:pk>/", views.TicTacToeMatchView.as_view(), name="ttt-match"),
    path("ttt/<int:pk>/move/", views.TicTacToeMoveView.as_view(), name="ttt-move"),
    path("rps/challenge/<str:username>/", views.RockPaperScissorsChallengeView.as_view(), name="rps-challenge"),
    path("rps/<int:pk>/", views.RockPaperScissorsMatchView.as_view(), name="rps-match"),
    path("rps/<int:pk>/move/", views.RockPaperScissorsMoveView.as_view(), name="rps-move"),
]
