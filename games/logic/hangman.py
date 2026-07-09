import random

WORD_LIST = [
    "python", "django", "keyboard", "internet", "elephant", "mountain",
    "guitar", "rainbow", "volcano", "dolphin", "bicycle", "chocolate",
    "umbrella", "penguin", "sandwich", "telescope", "backpack", "firefly",
]

MAX_WRONG_GUESSES = 6


def initial_state():
    return {"word": random.choice(WORD_LIST), "guessed": [], "wrong": 0}


def apply_guess(state, letter):
    if letter in state["guessed"]:
        return state
    guessed = state["guessed"] + [letter]
    wrong = state["wrong"] + (0 if letter in state["word"] else 1)
    return {"word": state["word"], "guessed": guessed, "wrong": wrong}


def display_word(state):
    return [letter if letter in state["guessed"] else None for letter in state["word"]]


def game_status(state):
    """Returns "won", "lost", or "playing"."""
    if state["wrong"] >= MAX_WRONG_GUESSES:
        return "lost"
    if all(letter in state["guessed"] for letter in state["word"]):
        return "won"
    return "playing"
