# calls/views.py
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import AgoraCallHistory
from calls.serializers import *
from calls.utils import build_agora_token

class IsAuthenticatedOrService(permissions.BasePermission):
 
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        # allow for webhook endpoint; actual verification will be inside the view
        return view.__class__.__name__ == "AgoraWebhookView"

from calls.utils import generate_agora_token
import threading
import time
from executives.models import Executive
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class CallInitiateView(APIView):
    def post(self, request):
        serializer = CallInitiateSerializer(data=request.data)
        if serializer.is_valid():
            executive_id = serializer.validated_data['executive_id']
            channel_name = serializer.validated_data['channel_name']
            caller_uid = serializer.validated_data['caller_uid']

            # Get executive
            executive = get_object_or_404(Executive, id=executive_id)

            # Validations
            validation_error = self.validate_executive(executive)
            if validation_error:
                return validation_error

            # Mark executive as on call
            executive.on_call = True
            executive.save(update_fields=["on_call"])

            # Generate tokens for both caller and executive
            caller_token = generate_agora_token(channel_name, caller_uid)
            callee_uid = caller_uid + 1000  # Simple UID generation
            executive_token = generate_agora_token(channel_name, callee_uid)

            # Create call history
            call_history = AgoraCallHistory.objects.create(
                executive=executive,
                channel_name=channel_name,
                uid=caller_uid,
                callee_uid=callee_uid,
                token=caller_token,
                executive_token=executive_token,
                status="pending",
                is_active=True,
                user=request.user
            )

            # Send WebSocket notification
            self.send_incoming_call_notification(
                executive_id, call_history, request.user
            )

            # Schedule missed call check (but don't use threading)
            self.schedule_missed_call_check(call_history.id)

            return Response({
                "id": call_history.id,
                "executive_id": executive_id,
                "channel_name": channel_name,
                "caller_uid": caller_uid,
                "token": caller_token,
                "status": "pending"
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def validate_executive(self, executive):
        """Validate executive availability"""
        if not executive.is_online:
            return Response({"detail": "Executive is offline"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        if executive.is_banned:
            return Response({"detail": "Executive is banned"}, 
                          status=status.HTTP_403_FORBIDDEN)
        if executive.is_suspended:
            return Response({"detail": "Executive is suspended"}, 
                          status=status.HTTP_403_FORBIDDEN)
        if executive.on_call:
            return Response({"detail": "Executive is on another call"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        return None

    def send_incoming_call_notification(self, executive_id, call_history, caller):
        """Send incoming call notification via WebSocket"""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"executive_{executive_id}",
                    {
                        "type": "incoming_call",
                        "call_id": call_history.id,
                        "channel_name": call_history.channel_name,
                        "caller_name": getattr(caller, "first_name", "Unknown"),
                        "caller_uid": call_history.uid,
                        "executive_token": call_history.executive_token,
                        "callee_uid": call_history.callee_uid,
                        "timestamp": call_history.start_time.isoformat()
                    }
                )
        except Exception as e:
            print(f"WebSocket notification failed: {e}")

    def schedule_missed_call_check(self, call_id):
        """Schedule missed call check using Celery or similar"""
        # Use Celery task instead of threading
        from .tasks import mark_call_as_missed
        mark_call_as_missed.apply_async(args=[call_id], countdown=30)



class GetCallByChannelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, channel_name):
        try:
            call = AgoraCallHistory.objects.get(channel_name=channel_name)
        except AgoraCallHistory.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)
        return Response(CallDetailSerializer(call).data)


class MarkJoinedView(APIView):
   
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, channel_name):
        try:
            call = AgoraCallHistory.objects.get(channel_name=channel_name, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"detail": "Active call not found"}, status=404)
        call.mark_joined()
        return Response({"ok": True})


class EndCallView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already ended"}, status=404)

        call.end_call(ender="client")
        
        # Send WebSocket notifications with error handling
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                # Notify both parties
                caller_group = f"user_client_{call.user_id}"
                executive_group = f"user_executive_{call.executive_id}"
                
                for group_name in [caller_group, executive_group]:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'call_ended',
                            'call_id': call_id,
                            'reason': 'Call ended by user',
                            'ended_by': 'client'
                        }
                    )
        except Exception as e:
            print(f"WebSocket end call notification failed: {e}")

        return Response({"ok": True, "message": "Call ended"})


class AgoraWebhookView(APIView):

    authentication_classes = []           # webhook usually comes unauthenticated
    permission_classes = [IsAuthenticatedOrService]

    def post(self, request):
        s = WebhookSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = s.validated_data

        event = payload["eventType"]
        channel = payload["channelName"]

        try:
            call = AgoraCallHistory.objects.get(channel_name=channel)
        except AgoraCallHistory.DoesNotExist:
            # Might be a late callback for a deleted call; ignore
            return Response({"ok": True})

        if event in ("user.joined", "channel.firstUserJoined"):
            call.mark_joined()

        elif event in ("user.left", "channel.idle", "channel.destroyed"):
            # Use an idempotent request_id derived from event+timestamp if provided
            req_id = f"webhook:{event}:{payload.get('timestamp', timezone.now().isoformat())}"
            call.end_call(ender="webhook", request_id=req_id)

        # You may persist heartbeat / last activity timestamp
        call.last_heartbeat = timezone.now()
        call.save(update_fields=["last_heartbeat"])
        return Response({"ok": True})

class CallJoinView(APIView):
    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or inactive"}, status=status.HTTP_404_NOT_FOUND)

        callee_uid = request.data.get("callee_uid")
        if not callee_uid:
            return Response({"error": "callee_uid is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Generate token for executive
        executive_token = generate_agora_token(call.channel_name, callee_uid)

        # Update call record
        call.callee_uid = callee_uid
        call.executive_token = executive_token
        call.status = "joined"
        call.joined_at = timezone.now()
        call.save()

        return Response({
            "id": call.id,
            "channel_name": call.channel_name,
            "status": call.status,
            "uid": call.uid,  # caller
            "callee_uid": call.callee_uid,  
            "token": call.token,  # caller token
            "executive_token": call.executive_token,  # executive token
            "joined_at": call.joined_at,
        }, status=status.HTTP_200_OK)


class RejectCallView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already inactive"}, status=404)

        call.status = "rejected"
        call.is_active = False
        call.save()

        return Response({"ok": True, "message": "Call rejected"})

class EndCallView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already ended"}, status=404)

        call.end_call(ender="client")
        return Response({"ok": True, "message": "Call ended"})

from users.models import UserProfile
from rest_framework import generics
from django.db.models import Avg

#Create rating for executive
class CreateCallRatingAPIView(APIView):
    def post(self, request, user_id, executive_id):
        try:
            user = UserProfile.objects.get(id=user_id)
            executive = Executive.objects.get(id=executive_id)
        except (UserProfile.DoesNotExist, Executive.DoesNotExist):
            return Response({"error": "User or Executive not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data['user'] = user.id
        data['executive'] = executive.id

        serializer = CallRatingSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#All user ratings

class CallRatingListAPIView(generics.ListAPIView):
    queryset = CallRating.objects.filter(is_deleted=False)
    serializer_class = CallRatingSerializer

#  Ratings for an executive

class ExecutiveRatingsAPIView(generics.ListAPIView):
    serializer_class = CallRatingSerializer

    def get_queryset(self):
        executive_id = self.kwargs['executive_id']
        return CallRating.objects.filter(executive_id=executive_id, is_deleted=False)
    

# Ratings for a user
class UserRatingsAPIView(generics.ListAPIView):
    serializer_class = CallRatingSerializer

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        return CallRating.objects.filter(user_id=user_id, is_deleted=False)
    
#  Average rating for an executive
class ExecutiveAverageRatingAPIView(APIView):
    def get(self, request, executive_id):
        avg_rating = CallRating.objects.filter(
            executive_id=executive_id, is_deleted=False
        ).aggregate(average=Avg('stars'))['average']

        return Response({
            "executive_id": executive_id,
            "average_rating": round(avg_rating, 2) if avg_rating else 0
        }, status=status.HTTP_200_OK)