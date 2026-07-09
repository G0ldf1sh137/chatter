from .exceptions import InvalidMove

WINNING_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),             # diagonals
]


def initial_state():
    return {"board": [None] * 9}


def apply_move(state, cell, symbol):
    board = state["board"]
    if not (0 <= cell < 9):
        raise InvalidMove("Cell out of range.")
    if board[cell] is not None:
        raise InvalidMove("Cell already taken.")
    board = list(board)
    board[cell] = symbol
    return {"board": board}


def check_winner(state):
    """Returns "X", "O", "draw", or None if the game is still in progress."""
    board = state["board"]
    for a, b, c in WINNING_LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    if all(cell is not None for cell in board):
        return "draw"
    return None
