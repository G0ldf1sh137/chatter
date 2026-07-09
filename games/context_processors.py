from . import stats


def your_turn_count(request):
    if not request.user.is_authenticated:
        return {}
    return {"your_turn_count": stats.your_turn_count(request.user)}
