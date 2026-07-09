import random

from .exceptions import InvalidMove

WORD_LIST = [
    "apple", "beach", "chair", "dance", "eagle", "flame", "grape", "house",
    "input", "joker", "knife", "lemon", "mango", "night", "ocean", "piano",
    "queen", "river", "smile", "table", "unity", "voice", "water", "young",
    "bread", "cloud", "dream", "field", "glory", "heart", "ideal", "jolly",
    "known", "large", "money", "noble", "olive", "peace", "quiet", "reach",
    "sunny", "trust", "usual", "value", "world", "yield", "zesty", "amber",
    "brave", "crisp",
]

MAX_GUESSES = 6
WORD_LENGTH = 5


def initial_state():
    return {"target": random.choice(WORD_LIST), "guesses": []}


def _feedback(target, guess):
    """Two-pass duplicate-letter-safe comparison: exact matches are marked
    and removed from the letter pool first, then remaining guess letters are
    marked "present" only while the pool still has that letter available."""
    pool = {}
    for ch in target:
        pool[ch] = pool.get(ch, 0) + 1

    result = [None] * WORD_LENGTH
    for i in range(WORD_LENGTH):
        if guess[i] == target[i]:
            result[i] = "correct"
            pool[guess[i]] -= 1

    for i in range(WORD_LENGTH):
        if result[i] is not None:
            continue
        if pool.get(guess[i], 0) > 0:
            result[i] = "present"
            pool[guess[i]] -= 1
        else:
            result[i] = "absent"
    return result


def apply_guess(state, guess):
    guess = guess.lower()
    if len(guess) != WORD_LENGTH or not guess.isalpha() or guess not in WORD_LIST:
        raise InvalidMove("Guess must be a valid 5-letter word.")
    feedback = _feedback(state["target"], guess)
    row = {"letters": [{"char": g, "status": f} for g, f in zip(guess, feedback)]}
    return {"target": state["target"], "guesses": state["guesses"] + [row]}


def game_status(state):
    """Returns "playing", "won", or "lost"."""
    if state["guesses"] and all(cell["status"] == "correct" for cell in state["guesses"][-1]["letters"]):
        return "won"
    if len(state["guesses"]) >= MAX_GUESSES:
        return "lost"
    return "playing"
