from django.urls import path

from .views import (
    AdminSendNotificationView,
    AdminResendNotificationView,
    AdminNotificationListView,
    AdminNotificationDeleteView,
)

urlpatterns = [
    path('admin/send/', AdminSendNotificationView.as_view(), name='admin-send-notification'),
    path('admin/<int:pk>/resend/', AdminResendNotificationView.as_view(), name='admin-resend-notification'),
    path('admin/history/', AdminNotificationListView.as_view(), name='admin-notification-history'),
    path('admin/<int:pk>/delete/', AdminNotificationDeleteView.as_view(), name='admin-delete-notification'),
]
