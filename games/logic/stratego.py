from .exceptions import InvalidMove

BOARD_SIZE = 8
PLAYER1_ROWS = range(0, 3)
PLAYER2_ROWS = range(5, 8)

# A simplified ~10-piece fleet instead of classic Stratego's 40, on an 8x8
# board instead of 10x10 - keeps placement to one click per piece (like
# Battleship's fleet) while preserving the rules that actually make it
# Stratego: ranked combat, the Spy-beats-Marshal exception, and Bombs that
# only a Miner can defuse.
FLEET = ["marshal", "captain", "lieutenant", "sergeant", "miner", "scout", "spy", "bomb", "bomb", "flag"]

# Every non-bomb, non-flag piece moves exactly one square orthogonally per
# turn (no Scout long-range move, unlike classic Stratego) - proportionate
# to this app's simplified rulesets elsewhere (Checkers' optional captures).
IMMOBILE_RANKS = ("bomb", "flag")

RANK_VALUES = {
    "spy": 0,
    "scout": 1,
    "miner": 2,
    "sergeant": 3,
    "lieutenant": 4,
    "captain": 5,
    "marshal": 6,
}


def deployment_rows(is_player1):
    return PLAYER1_ROWS if is_player1 else PLAYER2_ROWS


def initial_state():
    return {"phase": "placement", "boards": {}, "last_combat": None}


def _empty_board():
    return {"pieces": []}


def _copy_boards(boards):
    return {user_id: {"pieces": [dict(p) for p in board["pieces"]]} for user_id, board in boards.items()}


def pieces_for(state, user_id):
    return state["boards"].get(user_id, _empty_board())["pieces"]


def _piece_at(pieces, row, col):
    return next((p for p in pieces if p["row"] == row and p["col"] == col), None)


def is_fully_placed(state, user_id):
    return len(pieces_for(state, user_id)) >= len(FLEET)


def both_players_placed(state, player1_id, player2_id):
    return is_fully_placed(state, player1_id) and is_fully_placed(state, player2_id)


def apply_placement(state, user_id, row, col, valid_rows):
    if row not in valid_rows or not (0 <= col < BOARD_SIZE):
        raise InvalidMove("You can only deploy within your own three rows.")
    boards = _copy_boards(state["boards"])
    board = boards.setdefault(user_id, _empty_board())
    pieces = board["pieces"]
    if len(pieces) >= len(FLEET):
        raise InvalidMove("You've already placed your whole fleet.")
    if _piece_at(pieces, row, col) is not None:
        raise InvalidMove("There's already a piece there.")
    rank = FLEET[len(pieces)]
    pieces.append({"id": len(pieces), "rank": rank, "row": row, "col": col, "revealed": False})
    return {"phase": state["phase"], "boards": boards, "last_combat": state.get("last_combat")}


def resolve_combat(attacker, defender):
    """Returns "attacker_wins", "defender_wins", or "tie". `attacker` can
    never be a bomb or flag (apply_move rejects moving those)."""
    if defender["rank"] == "flag":
        return "attacker_wins"
    if defender["rank"] == "bomb":
        return "attacker_wins" if attacker["rank"] == "miner" else "defender_wins"
    if attacker["rank"] == "spy" and defender["rank"] == "marshal":
        return "attacker_wins"
    attacker_value = RANK_VALUES[attacker["rank"]]
    defender_value = RANK_VALUES[defender["rank"]]
    if attacker_value == defender_value:
        return "tie"
    return "attacker_wins" if attacker_value > defender_value else "defender_wins"


def apply_move(state, mover_id, opponent_id, from_row, from_col, to_row, to_col):
    boards = _copy_boards(state["boards"])
    mover_pieces = boards[mover_id]["pieces"]
    opponent_pieces = boards[opponent_id]["pieces"]

    piece = _piece_at(mover_pieces, from_row, from_col)
    if piece is None or piece["rank"] in IMMOBILE_RANKS:
        raise InvalidMove("No movable piece of yours at that position.")
    if not (0 <= to_row < BOARD_SIZE and 0 <= to_col < BOARD_SIZE):
        raise InvalidMove("Destination is off the board.")
    if abs(to_row - from_row) + abs(to_col - from_col) != 1:
        raise InvalidMove("Pieces move exactly one square, up, down, left, or right.")
    if _piece_at(mover_pieces, to_row, to_col) is not None:
        raise InvalidMove("You already have a piece there.")

    defender = _piece_at(opponent_pieces, to_row, to_col)
    last_combat = None
    if defender is None:
        piece["row"], piece["col"] = to_row, to_col
    else:
        outcome = resolve_combat(piece, defender)
        piece["revealed"] = True
        defender["revealed"] = True
        last_combat = {"attacker_rank": piece["rank"], "defender_rank": defender["rank"], "outcome": outcome}
        if outcome == "attacker_wins":
            opponent_pieces.remove(defender)
            piece["row"], piece["col"] = to_row, to_col
        elif outcome == "defender_wins":
            mover_pieces.remove(piece)
        else:
            mover_pieces.remove(piece)
            opponent_pieces.remove(defender)

    return {"phase": "battle", "boards": boards, "last_combat": last_combat}


def flag_captured(state, target_id):
    return not any(p["rank"] == "flag" for p in pieces_for(state, target_id))


def viewer_state(state, viewer_id, opponent_id):
    """A redacted view of `state` safe to hand to `viewer_id`'s template -
    an opponent piece's position is always visible (Stratego doesn't hide
    where pieces are, only what they are), but its rank is included only
    once combat has revealed it."""
    opponent_pieces = [
        {"row": p["row"], "col": p["col"], "rank": p["rank"] if p["revealed"] else None}
        for p in pieces_for(state, opponent_id)
    ]
    return {
        "phase": state["phase"],
        "your_pieces": pieces_for(state, viewer_id),
        "opponent_pieces": opponent_pieces,
        "last_combat": state.get("last_combat"),
    }
