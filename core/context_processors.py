try:
    from loans.models import Notification

    _loans_available = True
except ImportError:
    _loans_available = False


def notifications(request):
    if not _loans_available:
        return {"unread_notification_count": 0}
    if (
        request.user.is_authenticated
        and hasattr(request.user, "role")
        and request.user.role == "CUSTOMER"
    ):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {"unread_notification_count": count}
    return {"unread_notification_count": 0}
