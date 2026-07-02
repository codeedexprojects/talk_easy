from rest_framework import serializers

from .models import Notification


class AdminNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'body', 'image', 'audience',
            'total_recipients', 'success_count', 'failure_count', 'created_at',
        ]
        read_only_fields = ['total_recipients', 'success_count', 'failure_count', 'created_at']


class AdminSendNotificationSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    body = serializers.CharField()
    image = serializers.ImageField(required=False, allow_null=True)
    audience = serializers.ChoiceField(choices=Notification.AUDIENCE_CHOICES, default='all')
