from .exceptions import InvalidMove

ROWS = 6
COLS = 7

# Each direction pair, combined with its opposite via the range(1, 4) scan
# below, covers every line on the board exactly once starting from one of
# its endpoints - no need to also scan (0, -1), (-1, 0), (-1, -1), (-1, 1).
DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]


def initial_state():
    return {"board": [[None] * COLS for _ in range(ROWS)]}


def apply_move(state, column, symbol):
    if not (0 <= column < COLS):
        raise InvalidMove("Column out of range.")
    board = [list(row) for row in state["board"]]
    for row in range(ROWS - 1, -1, -1):
        if board[row][column] is None:
            board[row][column] = symbol
            return {"board": board}
    raise InvalidMove("Column is full.")


def check_winner(state):
    """Returns the winning symbol, "draw", or None if still in progress."""
    board = state["board"]
    for r in range(ROWS):
        for c in range(COLS):
            symbol = board[r][c]
            if symbol is None:
                continue
            for dr, dc in DIRECTIONS:
                if _four_in_a_row(board, r, c, dr, dc, symbol):
                    return symbol
    if all(board[r][c] is not None for r in range(ROWS) for c in range(COLS)):
        return "draw"
    return None


def _four_in_a_row(board, r, c, dr, dc, symbol):
    for i in range(1, 4):
        rr, cc = r + dr * i, c + dc * i
        if not (0 <= rr < ROWS and 0 <= cc < COLS) or board[rr][cc] != symbol:
            return False
    return True
