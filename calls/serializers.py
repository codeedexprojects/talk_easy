# calls/serializers.py
from rest_framework import serializers
from .models import AgoraCallHistory

class InitiateCallSerializer(serializers.Serializer):
    executive_id = serializers.IntegerField()
    channel_name = serializers.CharField(max_length=100)
    caller_uid = serializers.IntegerField()
    callee_uid = serializers.IntegerField(required=False, allow_null=True)

from rest_framework import serializers
from django.utils.timezone import localtime
import pytz

class CallDetailSerializer(serializers.ModelSerializer):
    start_time = serializers.SerializerMethodField()
    joined_at = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()

    class Meta:
        model = AgoraCallHistory
        fields = [
            "id", "channel_name", "status", "is_active",
            "token", "executive_token", "uid", "callee_uid",
            "start_time", "joined_at", "end_time", "duration",
            "coins_deducted", "coins_added"
        ]

    def get_start_time(self, obj):
        if obj.start_time:
            kolkata = pytz.timezone("Asia/Kolkata")
            return localtime(obj.start_time, kolkata).strftime("%I:%M %p %d-%m-%Y")
        return None

    def get_joined_at(self, obj):
        if obj.joined_at:
            kolkata = pytz.timezone("Asia/Kolkata")
            return localtime(obj.joined_at, kolkata).strftime("%I:%M %p %d-%m-%Y")
        return None

    def get_end_time(self, obj):
        if obj.end_time:
            kolkata = pytz.timezone("Asia/Kolkata")
            return localtime(obj.end_time, kolkata).strftime("%I:%M %p %d-%m-%Y")
        return None
    
class EndCallSerializer(serializers.Serializer):
    channel_name = serializers.CharField(max_length=100)
    request_id = serializers.CharField(max_length=64, required=False)  # for idempotency

class WebhookSerializer(serializers.Serializer):
    # Adjust to your Agora webhook payload structure
    eventType = serializers.CharField()
    channelName = serializers.CharField()
    uid = serializers.CharField()
    timestamp = serializers.DateTimeField(required=False)
    signature = serializers.CharField(required=False)  # if you sign with HMAC


class CallInitiateSerializer(serializers.Serializer):
    executive_id = serializers.IntegerField(required=True)
    channel_name = serializers.CharField(required=True)
    caller_uid = serializers.IntegerField(required=True)
