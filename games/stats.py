from django.db.models import Count, Max, Q

from .models import Match, SinglePlayerResult


def match_record(user, game):
    """Returns (wins, losses, draws) for a user in a given multiplayer game."""
    matches = Match.objects.filter(game=game, status=Match.Status.FINISHED).filter(
        Q(player1=user) | Q(player2=user)
    )
    wins = matches.filter(winner=user).count()
    draws = matches.filter(winner__isnull=True).count()
    losses = matches.exclude(winner=user).filter(winner__isnull=False).count()
    return wins, losses, draws


def hangman_wins(user):
    return SinglePlayerResult.objects.filter(
        player=user, game=SinglePlayerResult.Game.HANGMAN, won=True
    ).count()


def high_score_2048(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.GAME_2048)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def match_win_leaders(game, limit=10):
    return (
        Match.objects.filter(game=game, status=Match.Status.FINISHED, winner__isnull=False)
        .values("winner__username")
        .annotate(wins=Count("id"))
        .order_by("-wins")[:limit]
    )


def hangman_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.HANGMAN, won=True)
        .values("player__username")
        .annotate(wins=Count("id"))
        .order_by("-wins")[:limit]
    )


def game_2048_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.GAME_2048)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )


def snake_high_score(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.SNAKE)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def doodle_high_score(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.DOODLE_JUMP)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def snake_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.SNAKE)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )


def doodle_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.DOODLE_JUMP)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )


def wordle_high_score(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.WORDLE)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def wordle_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.WORDLE)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )
