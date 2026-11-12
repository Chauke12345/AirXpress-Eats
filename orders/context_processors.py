from .models import CustomerNotification


def customer_notification_count(request):
    count = 0
    if request.user.is_authenticated:
        count = CustomerNotification.objects.filter(
            customer=request.user,
            is_read=False,
        ).count()

    return {"customer_notification_unread_count": count}
