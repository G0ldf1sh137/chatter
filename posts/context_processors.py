from .views import unread_message_count, unread_notification_count


def unread_messages(request):
    if not request.user.is_authenticated:
        return {}
    return {"unread_message_count": unread_message_count(request.user)}


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {}
    return {"unread_notification_count": unread_notification_count(request.user)}
