from django.conf import settings
from django.db import models


class Match(models.Model):
    class Game(models.TextChoices):
        TIC_TAC_TOE = "ttt", "Tic-Tac-Toe"
        ROCK_PAPER_SCISSORS = "rps", "Rock-Paper-Scissors"
        CONNECT_FOUR = "connect4", "Connect Four"
        CHECKERS = "checkers", "Checkers"
        OTHELLO = "othello", "Othello"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"

    game = models.CharField(max_length=8, choices=Game.choices)
    player1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="games_as_player1")
    player2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="games_as_player2")
    state = models.JSONField(default=dict)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    # Null for games with no "whose turn" concept, e.g. Rock-Paper-Scissors,
    # where state["choices"] tracks who has already picked instead.
    turn = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # Null on a finished match means a draw.
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="games_won"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=~models.Q(player1=models.F("player2")), name="no_self_match"),
        ]
        indexes = [
            models.Index(fields=["player1", "status"]),
            models.Index(fields=["player2", "status"]),
        ]

    def __str__(self):
        return f"{self.get_game_display()} #{self.pk}: {self.player1} vs {self.player2}"

    def opponent_of(self, user):
        return self.player2 if user.id == self.player1_id else self.player1


class SinglePlayerResult(models.Model):
    class Game(models.TextChoices):
        HANGMAN = "hangman", "Word Guess"
        GAME_2048 = "2048", "2048"
        SNAKE = "snake", "Snake"
        DOODLE_JUMP = "doodle", "Doodle Jump"
        WORDLE = "wordle", "Wordle"

    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_results")
    game = models.CharField(max_length=8, choices=Game.choices)
    won = models.BooleanField(default=False)
    score = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        indexes = [
            models.Index(fields=["game", "-score"]),
            models.Index(fields=["player", "game"]),
        ]

    def __str__(self):
        return f"{self.player} {self.get_game_display()}: score={self.score} won={self.won}"
