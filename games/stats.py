from django.db.models import Count, Max, Q

from .logic import battleship, stratego
from .models import Match, SinglePlayerResult


def is_users_turn(match: Match, user):
    """Whether `user` currently has an action to take in an active match.

    Rock-Paper-Scissors has no match.turn (both players choose
    simultaneously - see the Match.turn field's docstring) - "your turn"
    there means "you haven't locked in a choice yet" instead. Battleship's
    and Stratego's placement phases are the same shape: both players place
    independently before match.turn means anything.
    """
    if match.status != Match.Status.ACTIVE:
        return False
    if match.game == Match.Game.ROCK_PAPER_SCISSORS:
        return not match.state.get("choices", {}).get(str(user.id))
    if match.game == Match.Game.BATTLESHIP and match.state.get("phase") == "placement":
        return not battleship.is_fully_placed(match.state, str(user.id))
    if match.game == Match.Game.STRATEGO and match.state.get("phase") == "placement":
        return not stratego.is_fully_placed(match.state, str(user.id))
    return match.turn_id == user.id


def your_turn_count(user):
    matches = Match.objects.filter(status=Match.Status.ACTIVE).filter(Q(player1=user) | Q(player2=user))
    return sum(1 for m in matches if is_users_turn(m, user))


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


def mastermind_high_score(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.MASTERMIND)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def mastermind_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.MASTERMIND)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )


def flappy_high_score(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.FLAPPY_BIRD)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def flappy_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.FLAPPY_BIRD)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )


def tetris_high_score(user):
    return (
        SinglePlayerResult.objects.filter(player=user, game=SinglePlayerResult.Game.TETRIS)
        .aggregate(Max("score"))["score__max"]
        or 0
    )


def tetris_leaders(limit=10):
    return (
        SinglePlayerResult.objects.filter(game=SinglePlayerResult.Game.TETRIS)
        .values("player__username")
        .annotate(high_score=Max("score"))
        .order_by("-high_score")[:limit]
    )
