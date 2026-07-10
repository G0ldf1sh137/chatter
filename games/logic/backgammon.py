import random

from .exceptions import InvalidMove

NUM_POINTS = 24
# p1 travels from point 23 toward 0 (bearing off past 0); p2 is the mirror
# image, traveling from 0 toward 23 (bearing off past 23) - one shared
# absolute coordinate frame rather than a per-player one, with direction as
# the only thing that differs.
DIRECTION = {"p1": -1, "p2": 1}
HOME_RANGE = {"p1": range(0, 6), "p2": range(18, 24)}
# Entering from the bar lands in the opponent's home board, at the point
# `die` pips in from the edge - the classic "point (25 - die)" rule,
# translated into this module's 0-indexed absolute points.
ENTRY_INDEX = {"p1": lambda die: 24 - die, "p2": lambda die: die - 1}


def _other(player):
    return "p2" if player == "p1" else "p1"


def initial_state():
    points = [{"owner": None, "count": 0} for _ in range(NUM_POINTS)]
    for index, count in ((23, 2), (12, 5), (7, 3), (5, 5)):
        points[index] = {"owner": "p1", "count": count}
    for index, count in ((0, 2), (11, 5), (16, 3), (18, 5)):
        points[index] = {"owner": "p2", "count": count}
    return {"points": points, "bar": {"p1": 0, "p2": 0}, "borne_off": {"p1": 0, "p2": 0}, "dice": []}


def _copy_state(state):
    return {
        "points": [dict(cell) for cell in state["points"]],
        "bar": dict(state["bar"]),
        "borne_off": dict(state["borne_off"]),
        "dice": list(state["dice"]),
    }


def roll_dice():
    a, b = random.randint(1, 6), random.randint(1, 6)
    return [a, a, a, a] if a == b else [a, b]


def _land_on(state, dest, mover, opponent):
    cell = state["points"][dest]
    if cell["owner"] == opponent and cell["count"] > 1:
        raise InvalidMove("That point is blocked by the opponent.")
    if cell["owner"] == opponent and cell["count"] == 1:
        state["bar"][opponent] = state["bar"].get(opponent, 0) + 1
        cell["owner"] = mover
        cell["count"] = 1
    else:
        cell["owner"] = mover
        cell["count"] += 1


def _remove_from(state, source, mover):
    cell = state["points"][source]
    cell["count"] -= 1
    if cell["count"] == 0:
        cell["owner"] = None


def _all_in_home(state, mover):
    if state["bar"].get(mover, 0) > 0:
        return False
    home = HOME_RANGE[mover]
    return all(
        index in home for index, cell in enumerate(state["points"]) if cell["owner"] == mover and cell["count"] > 0
    )


def _pips_to_bear_off(mover, point):
    return point + 1 if mover == "p1" else NUM_POINTS - point


def _no_checker_further_from_home(state, mover, source):
    if mover == "p1":
        further = range(source + 1, 6)
    else:
        further = range(18, source)
    return not any(state["points"][q]["owner"] == mover and state["points"][q]["count"] > 0 for q in further)


def _can_bear_off(state, mover, source, die_value):
    if not _all_in_home(state, mover):
        return False
    required = _pips_to_bear_off(mover, source)
    if die_value == required:
        return True
    if die_value > required:
        return _no_checker_further_from_home(state, mover, source)
    return False


def apply_move(state, mover, source, die_value):
    """`source` is a point index (0-23) or the literal string "bar"."""
    if die_value not in state["dice"]:
        raise InvalidMove("That die value isn't available.")
    if state["bar"].get(mover, 0) > 0 and source != "bar":
        raise InvalidMove("You must re-enter your checkers from the bar before making any other move.")

    state = _copy_state(state)
    opponent = _other(mover)
    direction = DIRECTION[mover]

    if source == "bar":
        if state["bar"].get(mover, 0) <= 0:
            raise InvalidMove("You have no checkers on the bar.")
        dest = ENTRY_INDEX[mover](die_value)
        _land_on(state, dest, mover, opponent)
        state["bar"][mover] -= 1
    else:
        if not (0 <= source < NUM_POINTS):
            raise InvalidMove("Point out of range.")
        if state["points"][source]["owner"] != mover or state["points"][source]["count"] <= 0:
            raise InvalidMove("You don't have a checker there.")
        dest = source + direction * die_value
        if 0 <= dest < NUM_POINTS:
            _land_on(state, dest, mover, opponent)
            _remove_from(state, source, mover)
        else:
            if not _can_bear_off(state, mover, source, die_value):
                raise InvalidMove("You can't bear off that checker yet.")
            _remove_from(state, source, mover)
            state["borne_off"][mover] = state["borne_off"].get(mover, 0) + 1

    state["dice"].remove(die_value)
    return state


def _has_legal_move_for_die(state, mover, die_value):
    opponent = _other(mover)
    direction = DIRECTION[mover]
    if state["bar"].get(mover, 0) > 0:
        dest = ENTRY_INDEX[mover](die_value)
        return not (state["points"][dest]["owner"] == opponent and state["points"][dest]["count"] > 1)
    for index, cell in enumerate(state["points"]):
        if cell["owner"] != mover or cell["count"] <= 0:
            continue
        dest = index + direction * die_value
        if 0 <= dest < NUM_POINTS:
            if not (state["points"][dest]["owner"] == opponent and state["points"][dest]["count"] > 1):
                return True
        elif _can_bear_off(state, mover, index, die_value):
            return True
    return False


def any_legal_move(state, mover):
    return any(_has_legal_move_for_die(state, mover, die_value) for die_value in set(state["dice"]))


def start_turn(state, mover):
    """Rolls dice for `mover`. If their whole roll has no legal move
    anywhere, forfeit immediately and roll for the opponent instead -
    repeated defensively (capped) in case that happens more than once,
    though a realistic position essentially never blocks every die value
    for both players at once. Returns (new_state, actual_mover)."""
    state = _copy_state(state)
    current = mover
    for _ in range(6):
        state["dice"] = roll_dice()
        if any_legal_move(state, current):
            return state, current
        current = _other(current)
    state["dice"] = []
    return state, current


def is_game_over(state, mover):
    return state["borne_off"].get(mover, 0) >= 15
