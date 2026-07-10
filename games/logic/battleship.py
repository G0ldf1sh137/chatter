from .exceptions import InvalidMove

BOARD_SIZE = 8
# A simplified 4-ship fleet (11 cells on a 64-cell board) rather than the
# full 5-ship/10x10 classic set - keeps placement to 4 form submissions per
# player and the board small enough to render without JS, same
# proportionality tradeoff as Checkers' simplified no-forced-capture ruleset.
FLEET = [4, 3, 2, 2]


def initial_state():
    return {"phase": "placement", "boards": {}}


def _empty_board():
    return {"ships": [], "shots_against": []}


def _copy_boards(boards):
    return {
        user_id: {
            "ships": [list(ship) for ship in board["ships"]],
            "shots_against": [list(cell) for cell in board["shots_against"]],
        }
        for user_id, board in boards.items()
    }


def ships_for(state, user_id):
    return state["boards"].get(user_id, _empty_board())["ships"]


def is_fully_placed(state, user_id):
    return len(ships_for(state, user_id)) >= len(FLEET)


def both_players_placed(state, player1_id, player2_id):
    return is_fully_placed(state, player1_id) and is_fully_placed(state, player2_id)


def _ship_cells(row, col, orientation, length):
    if orientation == "h":
        return [[row, col + i] for i in range(length)]
    return [[row + i, col] for i in range(length)]


def apply_placement(state, user_id, row, col, orientation):
    if orientation not in ("h", "v"):
        raise InvalidMove("Orientation must be horizontal or vertical.")
    boards = _copy_boards(state["boards"])
    board = boards.setdefault(user_id, _empty_board())
    placed = board["ships"]
    if len(placed) >= len(FLEET):
        raise InvalidMove("You've already placed all your ships.")
    length = FLEET[len(placed)]
    cells = _ship_cells(row, col, orientation, length)
    if any(not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE) for r, c in cells):
        raise InvalidMove("Ship doesn't fit on the board.")
    occupied = {(r, c) for ship in placed for r, c in ship}
    if any((r, c) in occupied for r, c in cells):
        raise InvalidMove("Ships can't overlap.")
    placed.append(cells)
    return {"phase": state["phase"], "boards": boards}


def apply_shot(state, target_id, row, col):
    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        raise InvalidMove("Shot must be on the board.")
    boards = _copy_boards(state["boards"])
    target_board = boards.setdefault(target_id, _empty_board())
    if [row, col] in target_board["shots_against"]:
        raise InvalidMove("You've already fired at that cell.")
    target_board["shots_against"].append([row, col])
    return {"phase": "battle", "boards": boards}


def is_hit(state, target_id, row, col):
    return any([row, col] in ship for ship in ships_for(state, target_id))


def all_ships_sunk(state, target_id):
    board = state["boards"].get(target_id, _empty_board())
    all_cells = {tuple(cell) for ship in board["ships"] for cell in ship}
    shots = {tuple(shot) for shot in board["shots_against"]}
    return bool(all_cells) and all_cells <= shots


def viewer_state(state, viewer_id, opponent_id):
    """A redacted view of `state` safe to hand to `viewer_id`'s template -
    the opponent's ship coordinates are never included, only which of the
    viewer's own shots against them were hits or misses."""
    viewer_board = state["boards"].get(viewer_id, _empty_board())
    opponent_board = state["boards"].get(opponent_id, _empty_board())
    opponent_ship_cells = {tuple(cell) for ship in opponent_board["ships"] for cell in ship}
    return {
        "phase": state["phase"],
        "your_ships": viewer_board["ships"],
        "shots_against_you": viewer_board["shots_against"],
        "your_shots": [
            {"row": r, "col": c, "hit": (r, c) in opponent_ship_cells}
            for r, c in (tuple(cell) for cell in opponent_board["shots_against"])
        ],
        "your_ships_placed": len(viewer_board["ships"]),
        "opponent_ships_placed": len(opponent_board["ships"]),
    }
