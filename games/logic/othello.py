from .exceptions import InvalidMove

BOARD_SIZE = 8
DIRECTIONS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def initial_state():
    board = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    board[3][3] = "W"
    board[3][4] = "B"
    board[4][3] = "B"
    board[4][4] = "W"
    return {"board": board}


def _flips_for_move(board, row, col, player):
    """Cells that would flip if `player` places at (row, col). Empty means the
    move is illegal - Othello moves must bracket at least one opponent piece."""
    if board[row][col] is not None:
        return []
    opponent = "W" if player == "B" else "B"
    all_flips = []
    for dr, dc in DIRECTIONS:
        line = []
        r, c = row + dr, col + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == opponent:
            line.append((r, c))
            r, c = r + dr, c + dc
        if line and 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
            all_flips.extend(line)
    return all_flips


def legal_moves(state, player):
    board = state["board"]
    return [
        (r, c)
        for r in range(BOARD_SIZE)
        for c in range(BOARD_SIZE)
        if board[r][c] is None and _flips_for_move(board, r, c, player)
    ]


def apply_move(state, row, col, player):
    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        raise InvalidMove("Cell out of range.")
    flips = _flips_for_move(state["board"], row, col, player)
    if not flips:
        raise InvalidMove("That cell doesn't bracket any opponent pieces.")
    new_board = [list(r) for r in state["board"]]
    new_board[row][col] = player
    for fr, fc in flips:
        new_board[fr][fc] = player
    return {"board": new_board}


def piece_counts(state):
    board = state["board"]
    black = sum(cell == "B" for row in board for cell in row)
    white = sum(cell == "W" for row in board for cell in row)
    return black, white


def next_turn_state(state, mover, opponent):
    """Returns ("continue", opponent), ("pass", mover), or
    ("game_over", winner_or_None). `mover`/`opponent` are "B"/"W" strings -
    the caller maps color back to whichever User that color belongs to.

    Othello has no "always alternate" turn order: a player with no legal
    move must pass back to the other player, and the game only ends once
    neither player has a legal move, with the winner decided by piece count
    (not by capturing everything or being unable to move, unlike Checkers).
    """
    if legal_moves(state, opponent):
        return ("continue", opponent)
    if legal_moves(state, mover):
        return ("pass", mover)
    black, white = piece_counts(state)
    if black == white:
        return ("game_over", None)
    return ("game_over", "B" if black > white else "W")
