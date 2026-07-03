from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile

from executives.permissions import IsAdminUser
from executives.models import Executive
from users.models import UserProfile

from .models import Notification
from .serializers import AdminSendNotificationSerializer, AdminNotificationSerializer
from .utils import send_bulk_fcm_notification


def _collect_tokens(audience):
    tokens = []
    if audience in ('all', 'users'):
        tokens += list(
            UserProfile.objects.exclude(fcm_token__isnull=True)
            .exclude(fcm_token='')
            .values_list('fcm_token', flat=True)
        )
    if audience in ('all', 'executives'):
        tokens += list(
            Executive.objects.exclude(fcm_token__isnull=True)
            .exclude(fcm_token='')
            .values_list('fcm_token', flat=True)
        )
    return tokens


def _dispatch_notification(notification, request):
    """
    Send `notification` via FCM to its audience's current tokens and
    record the resulting counts on it. Used by both send and resend.
    """
    image_url = None
    if notification.image:
        image_url = request.build_absolute_uri(notification.image.url)

    tokens = _collect_tokens(notification.audience)

    success_count, failure_count = send_bulk_fcm_notification(
        tokens,
        notification.title,
        notification.body,
        image_url=image_url,
        data={"type": "admin_broadcast", "notification_id": notification.id},
    )

    notification.total_recipients = len(tokens)
    notification.success_count = success_count
    notification.failure_count = failure_count
    notification.save(update_fields=['total_recipients', 'success_count', 'failure_count'])


class AdminSendNotificationView(APIView):
    """
    POST /notifications/admin/send/
    Admin broadcasts a push notification (with optional image) to all users,
    all executives, or both, using each recipient's stored FCM token.
    """
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        serializer = AdminSendNotificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        notification = Notification.objects.create(
            title=serializer.validated_data['title'],
            body=serializer.validated_data['body'],
            image=serializer.validated_data.get('image'),
            audience=serializer.validated_data['audience'],
            sent_by=request.user,
        )

        _dispatch_notification(notification, request)

        return Response(
            {
                "status": True,
                "message": "Notification sent",
                "data": AdminNotificationSerializer(notification, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminResendNotificationView(APIView):
    """
    POST /notifications/admin/<id>/resend/
    Re-send a previously sent notification (same title/body/image/audience)
    as a new history entry, targeting whoever currently holds an FCM token
    for that audience.
    """
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request, pk):
        original = get_object_or_404(Notification, pk=pk)

        notification = Notification.objects.create(
            title=original.title,
            body=original.body,
            audience=original.audience,
            sent_by=request.user,
        )
        if original.image:
            # Copy into a new file so this row owns an independent image —
            # deleting either notification later won't break the other's image.
            notification.image.save(
                original.image.name.rsplit('/', 1)[-1],
                ContentFile(original.image.read()),
                save=True,
            )

        _dispatch_notification(notification, request)

        return Response(
            {
                "status": True,
                "message": "Notification resent",
                "data": AdminNotificationSerializer(notification, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminNotificationListView(APIView):
    """
    GET /notifications/admin/history/
    List previously sent admin broadcast notifications, most recent first.
    """
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        notifications = Notification.objects.all()
        serializer = AdminNotificationSerializer(notifications, many=True, context={"request": request})
        return Response({"status": True, "data": serializer.data}, status=status.HTTP_200_OK)


class AdminNotificationDeleteView(APIView):
    """
    DELETE /notifications/admin/<id>/delete/
    Remove a notification record (and its image) from history.
    Does not recall the push already delivered to devices.
    """
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk)
        if notification.image:
            notification.image.delete(save=False)
        notification.delete()
        return Response({"status": True, "message": "Notification deleted"}, status=status.HTTP_200_OK)
