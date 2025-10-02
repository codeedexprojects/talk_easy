# from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import AgoraCallHistory

# @shared_task
def mark_call_as_missed(call_id):
    """Mark call as missed after timeout"""
    try:
        call = AgoraCallHistory.objects.get(id=call_id, status="pending")
        call.status = "missed"
        call.is_active = False
        call.end_time = timezone.now()
        call.save(update_fields=["status", "is_active", "end_time"])
        
        call.executive.on_call = False
        call.executive.save(update_fields=["on_call"])


        channel_layer = get_channel_layer()
        if channel_layer:

            async_to_sync(channel_layer.group_send)(
                f"executive_{call.executive.id}",
                {"type": "call_missed", "call_id": call_id}
            )

            async_to_sync(channel_layer.group_send)(
                f"user_{call.user.id}",
                {"type": "call_missed", "call_id": call_id}
            )
    except AgoraCallHistory.DoesNotExist:
        pass
