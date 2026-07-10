import random

from .exceptions import InvalidMove

COLORS = ["red", "orange", "yellow", "green", "blue", "purple"]
CODE_LENGTH = 4
MAX_GUESSES = 10


def initial_state():
    secret = [random.choice(COLORS) for _ in range(CODE_LENGTH)]
    return {"secret": secret, "guesses": []}


def _feedback(secret, guess):
    """Classic Mastermind scoring: black pegs are exact position+color
    matches; white pegs are correct colors in the wrong position, counted
    from what's left after black pegs are set aside - the reference
    algorithm for handling repeated colors correctly (matching each color
    at most min(remaining in secret, remaining in guess) times, the same
    "set aside exact matches, then count what's left" shape as Wordle's
    duplicate-letter handling, just with aggregate counts instead of a
    per-position status)."""
    black = sum(s == g for s, g in zip(secret, guess))

    secret_leftover = {}
    guess_leftover = {}
    for s, g in zip(secret, guess):
        if s != g:
            secret_leftover[s] = secret_leftover.get(s, 0) + 1
            guess_leftover[g] = guess_leftover.get(g, 0) + 1

    white = sum(min(count, secret_leftover.get(color, 0)) for color, count in guess_leftover.items())
    return black, white


def apply_guess(state, guess):
    if len(guess) != CODE_LENGTH or any(color not in COLORS for color in guess):
        raise InvalidMove(f"Guess must be exactly {CODE_LENGTH} colors from {', '.join(COLORS)}.")
    black, white = _feedback(state["secret"], guess)
    row = {"pegs": list(guess), "black": black, "white": white}
    return {"secret": state["secret"], "guesses": state["guesses"] + [row]}


def game_status(state):
    """Returns "playing", "won", or "lost"."""
    if state["guesses"] and state["guesses"][-1]["black"] == CODE_LENGTH:
        return "won"
    if len(state["guesses"]) >= MAX_GUESSES:
        return "lost"
    return "playing"
