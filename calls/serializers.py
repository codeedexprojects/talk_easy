# calls/serializers.py
from rest_framework import serializers
from .models import AgoraCallHistory,CallRating

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
    request_id = serializers.CharField(max_length=64, required=False)  

class AgoraWebhookPayloadSerializer(serializers.Serializer):
    """Nested `payload` object inside an Agora Notifications callback body."""
    channelName = serializers.CharField()
    uid = serializers.IntegerField(required=False)
    ts = serializers.IntegerField(required=False)  # Unix seconds, when the event occurred on Agora's RTC server
    clientSeq = serializers.IntegerField(required=False)
    lastUid = serializers.IntegerField(required=False)  # present only on eventType 102 (channel destroy)


class WebhookSerializer(serializers.Serializer):
    """
    Matches Agora's real Notifications callback body exactly (see
    https://docs.agora.io — 'Receive notifications about channel events').
    eventType is numeric — e.g. 107/108 for communication-mode join/leave,
    102 for channel destroy — NOT the friendly strings previously assumed here.
    """
    noticeId = serializers.CharField(required=False)
    productId = serializers.IntegerField(required=False)
    eventType = serializers.IntegerField()
    notifyMs = serializers.IntegerField(required=False)  # Unix ms when Agora SENT the callback (not when the event happened)
    payload = AgoraWebhookPayloadSerializer()


class CallInitiateSerializer(serializers.Serializer):
    executive_id = serializers.IntegerField(required=True)
    channel_name = serializers.CharField(required=True)
    caller_uid = serializers.IntegerField(required=True)
    




class CallRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallRating
        fields = '__all__'
        read_only_fields = ['created_at', 'is_deleted']


class CallHistorySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    executive_name = serializers.CharField(source="executive.name", read_only=True)
    exe_username = serializers.CharField(source="executive.username", read_only=True)
    user_id = serializers.CharField(source="user.user_id", read_only=True)
    executive_id = serializers.CharField(source="executive.executive_id", read_only=True)
    is_blocked = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    calling_time = serializers.SerializerMethodField()

    class Meta:
        model = AgoraCallHistory
        fields = [
            "id", "channel_name", "status", "start_time", "end_time","token","executive_token",
            "duration", "calling_time",
            "duration_seconds", "coins_deducted", "executive_earnings","callee_uid",
            "user_name", "executive_name", "exe_username", "user","user_id","executive","executive_id","is_blocked"
        ]

    def get_start_time(self, obj):
        if obj.start_time:
            kolkata = pytz.timezone("Asia/Kolkata")
            return localtime(obj.start_time, kolkata).strftime("%I:%M %p %d-%m-%Y")
        return None

    def get_end_time(self, obj):
        if obj.end_time:
            kolkata = pytz.timezone("Asia/Kolkata")
            return localtime(obj.end_time, kolkata).strftime("%I:%M %p %d-%m-%Y")
        return None

    def get_duration(self, obj):
        mins, secs = divmod(obj.duration_seconds or 0, 60)
        return f"{mins:02d}:{secs:02d}"

    def get_calling_time(self, obj):
        mins, secs = divmod(obj.duration_seconds or 0, 60)
        return f"{mins:02d}:{secs:02d}"

    def get_is_blocked(self, obj):
        from executives.models import BlockedusersByExecutive  
        blocked_entry = BlockedusersByExecutive.objects.filter(
            user=obj.user, executive=obj.executive, is_blocked=True
        ).first()
        return bool(blocked_entry)
    
class AgoraCallHistorySerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source="user.user_id", read_only=True)
    executive_id = serializers.CharField(source="executive.executive_id", read_only=True)

    class Meta:
        model = AgoraCallHistory
        fields = [
            "id",
            "channel_name",
            "uid",
            "callee_uid",
            "executive_token",
            "token",
            "status",
            "is_active",
            "start_time",
            "joined_at",
            "end_time",
            "duration_seconds",
            "coins_deducted",
            "executive_earnings",
            "coins_per_second",
            "amount_per_min",
            "user_id",
            "executive_id",
            "ended_by",
            "end_request_id",
        ]


class OngoingCallHistorySerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source="user.user_id", read_only=True)
    executive_id = serializers.CharField(source="executive.executive_id", read_only=True)
    executive_name = serializers.CharField(source="executive.name", read_only=True)
    executive_username = serializers.CharField(source="executive.username", read_only=True)
    duration = serializers.SerializerMethodField()
    user = serializers.IntegerField(source="user.id", read_only=True)
    executive = serializers.IntegerField(source="executive.id", read_only=True)

    class Meta:
        model = AgoraCallHistory
        fields = [
            "id",
            "channel_name",
            "uid",
            "callee_uid",
            "executive_token",
            "token",
            "status",
            "is_active",
            "start_time",
            "joined_at",
            "end_time",
            "duration_seconds",
            "duration",
            "coins_deducted",
            "executive_earnings",
            "coins_per_second",
            "amount_per_min",
            "user_id",
            "executive_id",
            "executive_name",
            "executive_username",
            "user",
            "executive",
            "ended_by",
            "end_request_id",
        ]

    def get_duration(self, obj):
        mins, secs = divmod(obj.duration_seconds or 0, 60)
        return f"{mins:02d}:{secs:02d}"