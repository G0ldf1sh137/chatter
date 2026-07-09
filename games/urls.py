from django.urls import path

from . import views

urlpatterns = [
    path("", views.GamesHubView.as_view(), name="games-hub"),
    path("leaderboard/", views.LeaderboardView.as_view(), name="games-leaderboard"),
    path("ttt/challenge/<str:username>/", views.TicTacToeChallengeView.as_view(), name="ttt-challenge"),
    path("ttt/<int:pk>/", views.TicTacToeMatchView.as_view(), name="ttt-match"),
    path("ttt/<int:pk>/move/", views.TicTacToeMoveView.as_view(), name="ttt-move"),
    path("rps/challenge/<str:username>/", views.RockPaperScissorsChallengeView.as_view(), name="rps-challenge"),
    path("rps/<int:pk>/", views.RockPaperScissorsMatchView.as_view(), name="rps-match"),
    path("rps/<int:pk>/move/", views.RockPaperScissorsMoveView.as_view(), name="rps-move"),
    path("connect4/challenge/<str:username>/", views.ConnectFourChallengeView.as_view(), name="connect4-challenge"),
    path("connect4/<int:pk>/", views.ConnectFourMatchView.as_view(), name="connect4-match"),
    path("connect4/<int:pk>/move/", views.ConnectFourMoveView.as_view(), name="connect4-move"),
    path("checkers/challenge/<str:username>/", views.CheckersChallengeView.as_view(), name="checkers-challenge"),
    path("checkers/<int:pk>/", views.CheckersMatchView.as_view(), name="checkers-match"),
    path("checkers/<int:pk>/move/", views.CheckersMoveView.as_view(), name="checkers-move"),
    path("hangman/new/", views.HangmanNewView.as_view(), name="hangman-new"),
    path("hangman/", views.HangmanPlayView.as_view(), name="hangman-play"),
    path("hangman/guess/", views.HangmanGuessView.as_view(), name="hangman-guess"),
    path("2048/", views.Game2048View.as_view(), name="2048-play"),
    path("2048/finish/", views.Game2048FinishView.as_view(), name="2048-finish"),
    path("snake/", views.SnakeView.as_view(), name="snake-play"),
    path("snake/finish/", views.SnakeFinishView.as_view(), name="snake-finish"),
    path("doodle/", views.DoodleJumpView.as_view(), name="doodle-play"),
    path("doodle/finish/", views.DoodleJumpFinishView.as_view(), name="doodle-finish"),
]
