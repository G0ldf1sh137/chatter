from .exceptions import InvalidMove

SIZE = 8

# Forward direction (row delta) for a non-king's *simple* move, per color.
FORWARD_ROW_DELTA = {"r": -1, "b": 1}

ALL_DIAGONALS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def initial_state():
    board = [[None] * SIZE for _ in range(SIZE)]
    for r in range(3):
        for c in range(SIZE):
            if (r + c) % 2 == 1:
                board[r][c] = "b"
    for r in range(5, SIZE):
        for c in range(SIZE):
            if (r + c) % 2 == 1:
                board[r][c] = "r"
    return {"board": board}


def _in_bounds(r, c):
    return 0 <= r < SIZE and 0 <= c < SIZE


def apply_move(state, from_pos, to_pos, player):
    """from_pos/to_pos are (row, col) tuples, player is "r" or "b".

    Captures ignore the forward-direction restriction even for non-king
    pieces (standard checkers convention: a man can always jump backward
    over an adjacent enemy piece, even though it can't step backward as a
    simple move) - this simplified ruleset doesn't state it explicitly, so
    it's called out here as the deliberate interpretation.
    """
    board = [list(row) for row in state["board"]]
    fr, fc = from_pos
    tr, tc = to_pos
    if not (_in_bounds(fr, fc) and _in_bounds(tr, tc)):
        raise InvalidMove("Position out of range.")

    piece = board[fr][fc]
    if piece is None or piece.lower() != player:
        raise InvalidMove("No piece belonging to you at that position.")
    if board[tr][tc] is not None:
        raise InvalidMove("Destination is occupied.")

    dr, dc = tr - fr, tc - fc
    if abs(dr) != abs(dc) or abs(dr) not in (1, 2):
        raise InvalidMove("Move must be one or two squares diagonally.")

    is_king = piece.isupper()

    if abs(dr) == 1:
        if not is_king and dr != FORWARD_ROW_DELTA[player]:
            raise InvalidMove("Non-king pieces can't move backward.")
    else:
        mr, mc = (fr + tr) // 2, (fc + tc) // 2
        captured = board[mr][mc]
        if captured is None or captured.lower() == player:
            raise InvalidMove("Must jump over an enemy piece to capture.")
        board[mr][mc] = None

    board[fr][fc] = None
    if not is_king and tr == (0 if player == "r" else SIZE - 1):
        piece = piece.upper()
    board[tr][tc] = piece
    return {"board": board}


def _simple_move_directions(piece):
    if piece.isupper():
        return ALL_DIAGONALS
    return [d for d in ALL_DIAGONALS if d[0] == FORWARD_ROW_DELTA[piece.lower()]]


def legal_moves_exist(state, player):
    board = state["board"]
    for r in range(SIZE):
        for c in range(SIZE):
            piece = board[r][c]
            if piece is None or piece.lower() != player:
                continue
            for dr, dc in _simple_move_directions(piece):
                tr, tc = r + dr, c + dc
                if _in_bounds(tr, tc) and board[tr][tc] is None:
                    return True
            for dr, dc in ALL_DIAGONALS:
                mr, mc = r + dr, c + dc
                tr, tc = r + 2 * dr, c + 2 * dc
                if (
                    _in_bounds(tr, tc)
                    and _in_bounds(mr, mc)
                    and board[mr][mc] is not None
                    and board[mr][mc].lower() != player
                    and board[tr][tc] is None
                ):
                    return True
    return False


def check_winner(state, next_player):
    """`next_player` is whoever is about to move. Returns the *other*
    player's color if `next_player` has no pieces or no legal moves, else
    None. No draw concept in this simplified (no-forced-capture) ruleset."""
    board = state["board"]
    other = "b" if next_player == "r" else "r"
    has_pieces = any(cell is not None and cell.lower() == next_player for row in board for cell in row)
    if not has_pieces:
        return other
    if not legal_moves_exist(state, next_player):
        return other
    return None
