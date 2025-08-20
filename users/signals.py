from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from executives.models import Executive
from executives.serializers import ExecutiveSerializer

def broadcast_executives():
    channel_layer = get_channel_layer()
    data = ExecutiveSerializer(Executive.objects.all().order_by('-created_at'), many=True).data
    async_to_sync(channel_layer.group_send)(
        "executives_group",
        {
            "type": "send_executive_update",
            "data": data
        }
    )

@receiver(post_save, sender=Executive)
def executive_saved(sender, instance, **kwargs):
    broadcast_executives()

@receiver(post_delete, sender=Executive)
def executive_deleted(sender, instance, **kwargs):
    broadcast_executives()
