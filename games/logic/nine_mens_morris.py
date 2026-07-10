from .exceptions import InvalidMove

# 24 points as three nested squares (ring 0=outer, 1=middle, 2=inner), 8
# points per ring (position 0-7 clockwise from the top-left corner - even
# positions are corners, odd positions are mid-sides). point_id = ring*8 +
# position. Adjacency and mills are generated from this ring/position math
# rather than hand-typed, to avoid the kind of transcription bug 24 magic
# literals would invite.
NUM_POINTS = 24
PIECES_PER_PLAYER = 9


def _neighbors(point_id):
    ring, position = point_id // 8, point_id % 8
    same_ring = [ring * 8 + (position - 1) % 8, ring * 8 + (position + 1) % 8]
    if position % 2 == 0:
        return same_ring  # corner: no cross-ring edges
    neighbors = list(same_ring)
    if ring > 0:
        neighbors.append((ring - 1) * 8 + position)
    if ring < 2:
        neighbors.append((ring + 1) * 8 + position)
    return neighbors


ADJACENCY = {point: _neighbors(point) for point in range(NUM_POINTS)}


def _mills():
    mills = []
    for ring in range(3):
        base = ring * 8
        mills.append((base + 0, base + 1, base + 2))
        mills.append((base + 2, base + 3, base + 4))
        mills.append((base + 4, base + 5, base + 6))
        mills.append((base + 6, base + 7, base + 0))
    for position in (1, 3, 5, 7):
        mills.append((0 * 8 + position, 1 * 8 + position, 2 * 8 + position))
    return mills


MILLS = _mills()


def _coords(ring, position):
    inset, high = ring, 6 - ring
    return {
        0: (inset, inset), 1: (3, inset), 2: (high, inset), 3: (high, 3),
        4: (high, high), 5: (3, high), 6: (inset, high), 7: (inset, 3),
    }[position]


# Unit-grid (0-6) coordinates per point, for the view to scale into pixels -
# kept here as plain geometry, not Django-specific, same as everywhere else
# a logic module stays presentation-agnostic.
POINT_COORDS = [_coords(point // 8, point % 8) for point in range(NUM_POINTS)]


def initial_state():
    return {"points": [None] * NUM_POINTS, "to_place": {}, "pending_removal": None}


def _copy_state(state):
    return {
        "points": list(state["points"]),
        "to_place": dict(state["to_place"]),
        "pending_removal": state["pending_removal"],
    }


def to_place_count(state, user_id):
    return state["to_place"].get(user_id, PIECES_PER_PLAYER)


def is_mill(points, point_id, user_id):
    return any(point_id in mill and all(points[p] == user_id for p in mill) for mill in MILLS)


def apply_move(state, user_id, from_point, to_point):
    """`from_point` is None for a placement; otherwise a slide (or a fly,
    once `user_id` is down to exactly 3 pieces on the board)."""
    if not (0 <= to_point < NUM_POINTS):
        raise InvalidMove("Point out of range.")
    state = _copy_state(state)
    points = state["points"]
    remaining_to_place = to_place_count(state, user_id)

    if remaining_to_place > 0:
        if from_point is not None:
            raise InvalidMove("You still have pieces to place - place, don't move.")
        if points[to_point] is not None:
            raise InvalidMove("That point is already occupied.")
        points[to_point] = user_id
        state["to_place"][user_id] = remaining_to_place - 1
    else:
        if from_point is None:
            raise InvalidMove("You've placed all your pieces - move one instead.")
        if not (0 <= from_point < NUM_POINTS):
            raise InvalidMove("Point out of range.")
        if points[from_point] != user_id:
            raise InvalidMove("You don't have a piece there.")
        if points[to_point] is not None:
            raise InvalidMove("That point is already occupied.")
        pieces_on_board = sum(1 for p in points if p == user_id)
        if pieces_on_board > 3 and to_point not in ADJACENCY[from_point]:
            raise InvalidMove("You can only move to an adjacent point (unless you're down to 3 pieces).")
        points[from_point] = None
        points[to_point] = user_id

    state["pending_removal"] = user_id if is_mill(points, to_point, user_id) else None
    return state


def removable_points(state, target_user_id):
    """Points belonging to `target_user_id` that are legal to remove - any
    of their pieces if all are in mills, else only the ones that aren't."""
    points = state["points"]
    occupied = {p for p in range(NUM_POINTS) if points[p] == target_user_id}
    protected = {p for p in occupied if is_mill(points, p, target_user_id)}
    return occupied if protected == occupied else occupied - protected


def apply_removal(state, remover_id, opponent_id, remove_point):
    if state.get("pending_removal") != remover_id:
        raise InvalidMove("No removal is pending.")
    if not (0 <= remove_point < NUM_POINTS) or state["points"][remove_point] != opponent_id:
        raise InvalidMove("That point doesn't have an opponent piece.")
    if remove_point not in removable_points(state, opponent_id):
        raise InvalidMove("That piece is protected by a mill.")
    state = _copy_state(state)
    state["points"][remove_point] = None
    state["pending_removal"] = None
    return state


def is_defeated_by_piece_count(state, user_id):
    pieces_on_board = sum(1 for p in state["points"] if p == user_id)
    return to_place_count(state, user_id) == 0 and pieces_on_board < 3


def has_legal_move(state, user_id):
    if to_place_count(state, user_id) > 0:
        return any(p is None for p in state["points"])
    points = state["points"]
    occupied = [p for p in range(NUM_POINTS) if points[p] == user_id]
    flying = len(occupied) == 3
    if flying:
        return any(p is None for p in points)
    return any(points[n] is None for p in occupied for n in ADJACENCY[p])


def is_game_over(state, opponent_id):
    """Call once the mover's whole turn (move, plus any removal) is
    resolved - True if `opponent_id` is now defeated (below 3 pieces) or
    has no legal move, meaning the mover just won. Same "is the next player
    stuck" shape as checkers.check_winner(state, next_player), simplified
    to a bool since the mover is always the winner when this fires."""
    return is_defeated_by_piece_count(state, opponent_id) or not has_legal_move(state, opponent_id)
