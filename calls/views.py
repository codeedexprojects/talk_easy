# calls/views.py
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

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
            try:
                executive = Executive.objects.get(id=executive_id)
            except Executive.DoesNotExist:
                return Response({"detail": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)

            # --- Validations ---
            if not executive.is_online:
                return Response({"detail": "Executive is offline"}, status=status.HTTP_400_BAD_REQUEST)
            if executive.is_banned:
                return Response({"detail": "Executive is banned"}, status=status.HTTP_403_FORBIDDEN)
            if executive.is_suspended:
                return Response({"detail": "Executive is suspended"}, status=status.HTTP_403_FORBIDDEN)
            if executive.on_call:
                return Response({"detail": "Executive is on another call"}, status=status.HTTP_400_BAD_REQUEST)

            # Mark executive as on call
            executive.on_call = True
            executive.save(update_fields=["on_call"])

            # Generate Agora token
            token = generate_agora_token(channel_name, caller_uid)

            # Save call history
            call_history = AgoraCallHistory.objects.create(
                executive=executive,
                channel_name=channel_name,
                uid=caller_uid,
                token=token,
                status="pending",
                is_active=True,
                start_time=timezone.now(),
                user=request.user
            )

            # --- WebSocket notification for incoming call ---
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"user_executive_{executive_id}",
                        {
                            "type": "incoming_call",
                            "call_id": call_history.id,
                            "channel_name": channel_name,
                            "caller_name": getattr(request.user, "first_name", "Unknown"),
                            "caller_uid": caller_uid,
                            "timestamp": call_history.start_time.isoformat()
                        }
                    )
            except Exception as e:
                print(f"WebSocket incoming_call failed: {e}")

            # --- Handle missed call after 30s if not picked ---
            def clear_on_call_if_not_joined(call_id, executive_id, caller_id):
                time.sleep(30)
                call = AgoraCallHistory.objects.filter(id=call_id, status="pending").first()
                if call:
                    call.status = "missed"
                    call.is_active = False
                    call.end_time = timezone.now()
                    call.save(update_fields=["status", "is_active", "end_time"])
                    Executive.objects.filter(id=executive_id).update(on_call=False)

                    try:
                        channel_layer = get_channel_layer()
                        if channel_layer:
                            # Notify executive
                            async_to_sync(channel_layer.group_send)(
                                f"user_executive_{executive_id}",
                                {
                                    "type": "call_missed",
                                    "call_id": call_id
                                }
                            )
                            # Notify caller
                            async_to_sync(channel_layer.group_send)(
                                f"user_client_{caller_id}",
                                {
                                    "type": "call_missed",
                                    "call_id": call_id
                                }
                            )
                    except Exception as e:
                        print(f"WebSocket call_missed failed: {e}")

            threading.Thread(
                target=clear_on_call_if_not_joined,
                args=(call_history.id, executive.id, request.user.id),
                daemon=True
            ).start()

            # --- Response ---
            return Response({
                "id": call_history.id,
                "executive_id": executive_id,
                "channel_name": channel_name,
                "caller_uid": caller_uid,
                "token": token,
                "status": "pending"
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            "callee_uid": call.callee_uid,  # now filled
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


