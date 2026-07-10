from .exceptions import InvalidMove

# A well-known starting position with no immediately obvious forced win -
# doesn't matter for a casual game, but nicer than picking arbitrary numbers.
STARTING_PILES = [3, 5, 7]


def initial_state():
    return {"piles": list(STARTING_PILES)}


def apply_move(state, pile_index, count):
    piles = state["piles"]
    if not (0 <= pile_index < len(piles)):
        raise InvalidMove("Pile out of range.")
    if not (1 <= count <= piles[pile_index]):
        raise InvalidMove("Must take at least one, and no more than the pile has left.")
    piles = list(piles)
    piles[pile_index] -= count
    return {"piles": piles}


def is_game_over(state):
    # Normal play convention: whoever takes the last stick wins - so once
    # every pile is empty, the player who just moved is the winner, decided
    # entirely by the caller (the mover), no separate "next player" check
    # needed the way Tic-Tac-Toe/Checkers need to scan for a winning line.
    return all(pile == 0 for pile in state["piles"])
