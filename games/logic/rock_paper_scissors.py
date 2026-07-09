CHOICES = ("rock", "paper", "scissors")

_BEATS = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper",
}


def determine_winner(choice_a, choice_b):
    """Returns "a", "b", or "draw"."""
    if choice_a == choice_b:
        return "draw"
    return "a" if _BEATS[choice_a] == choice_b else "b"
