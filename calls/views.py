# calls/views.py
import logging
import hmac
import hashlib
import datetime as dt
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
from executives.authentication import ExecutiveTokenAuthentication
from rest_framework.permissions import IsAuthenticated
from executives.models import ExecutiveStats
from executives.pricing import get_current_amount_per_min
from .pagination import CustomCallPagination
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAdminUser
from calls.utils import generate_agora_token
import time
from executives.models import Executive
from users.models import UserStats
from calls.utils import send_fcm_notification
from executives.permissions import IsAdminUser
import threading
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import AgoraCallHistory
from calls.serializers import CallInitiateSerializer
from calls.utils import generate_agora_token
from executives.models import Executive, ExecutiveStats
from users.models import UserStats

logger = logging.getLogger("calls")
class IsAuthenticatedOrService(permissions.BasePermission):
 
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        # Let the (unauthenticated) Agora webhook through here — it verifies
        # the request's HMAC signature itself in AgoraWebhookView.post via
        # _verify_agora_signature, since Agora never authenticates as a user.
        return view.__class__.__name__ == "AgoraWebhookView"



class CallInitiateView(APIView):
    def post(self, request):
        serializer = CallInitiateSerializer(data=request.data)
        if serializer.is_valid():
            executive_id = serializer.validated_data['executive_id']
            channel_name = serializer.validated_data['channel_name']
            caller_uid = serializer.validated_data['caller_uid']

            user = request.user
            try:
                user_stats = user.stats
            except UserStats.DoesNotExist:
                return Response({"message": "User stats not found"}, status=status.HTTP_400_BAD_REQUEST)

            if user_stats.coin_balance < 180:
                return Response({"message": "At least 180 coins required to start a call"}, status=status.HTTP_402_PAYMENT_REQUIRED)

            # The availability check and the on_call flip must be atomic and
            # row-locked together, otherwise two near-simultaneous requests for
            # the same executive can both read on_call=False before either
            # commits, and both get through (double-booking the executive).
            with transaction.atomic():
                executive = get_object_or_404(
                    Executive.objects.select_for_update(), id=executive_id
                )

                validation_error = self.validate_executive(executive)
                if validation_error:
                    return validation_error

                # Mark executive as on call
                executive.on_call = True
                executive.save(update_fields=["on_call"])

                # Generate caller token
                caller_token = generate_agora_token(channel_name, caller_uid)

                # Calculate callee_uid (executive's UID)
                callee_uid = caller_uid + 1000
                # Generate executive token with the predetermined UID
                executive_token = generate_agora_token(channel_name, callee_uid)

                # Get executive stats
                exec_stats, _ = ExecutiveStats.objects.get_or_create(executive=executive)
                rate_per_minute = get_current_amount_per_min(executive)
                coins_per_second = exec_stats.coins_per_second
                executive_code = executive.executive_id

                # Create call history
                call_history = AgoraCallHistory.objects.create(
                    executive=executive,
                    channel_name=channel_name,
                    uid=caller_uid,
                    callee_uid=callee_uid,
                    token=caller_token,
                    executive_token=executive_token,
                    status="ringing",
                    is_active=False,
                    user=user,
                    coins_per_second=coins_per_second,
                    amount_per_min=rate_per_minute
                )

            # Send WebSocket notification — logs internally if it fails
            self.send_incoming_call_notification(executive_id, call_history, user)

            fcm_sent = False
            fcm_error = None

            if executive.fcm_token:
                fcm_title = "talkeazy"
                fcm_body = f"New call from {getattr(user, 'user_id', 'Unknown')}"
                avatar_url = ""
                if user.dp_image:
                    avatar_url = request.build_absolute_uri(user.dp_image.url)

                fcm_data = {
                    "type": "incoming_call",
                    "call_id": str(call_history.id),
                    "caller_name": str(user.name or getattr(user, "user_id", "Unknown")),
                    "caller_number": str(getattr(user, "mobile_number", "") or "Unknown"),
                    "avatar": avatar_url,
                    "channel_name": str(call_history.channel_name),
                    "token": str(call_history.executive_token),
                    "agorauserid": str(call_history.callee_uid)
                }
                logger.info("[CALLS] Sending FCM notification to executive_id=%s (token=%s...)",
                            executive_id, str(executive.fcm_token)[:20])
                fcm_sent = send_fcm_notification(
                    executive.fcm_token,
                    fcm_title,
                    fcm_body,
                    fcm_data
                )
                if fcm_sent:
                    logger.info("[CALLS] FCM notification sent successfully for call_id=%s", call_history.id)
                else:
                    fcm_error = "FCM send failed — check server logs for exact error"
                    logger.warning("[CALLS] FCM notification FAILED for call_id=%s", call_history.id)
            else:
                fcm_error = "No FCM token available for executive"
                logger.warning("[CALLS] No FCM token for executive_id=%s — skipping FCM", executive_id)

            # Schedule missed call check (non-Celery)
            threading.Timer(30, self.mark_call_as_missed, args=[call_history.id]).start()

            # Calculate maximum talk time in seconds
            max_talk_time_seconds = 0
            if coins_per_second > 0:
                max_talk_time_seconds = int(user_stats.coin_balance // coins_per_second)

            return Response({
                "id": call_history.id,
                "executive_id": executive_id,
                "executive_code": executive_code,
                "channel_name": channel_name,
                "caller_uid": caller_uid,
                "token": caller_token,
                "callee_uid": callee_uid,
                "executive_token": executive_token,
                "status": "ringing",
                "coins_per_second": coins_per_second,
                "amount_per_min": str(rate_per_minute),
                "fcm_sent": fcm_sent,
                "fcm_error": fcm_error,
                "max_talk_time_seconds": max_talk_time_seconds
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def validate_executive(self, executive):
        if not executive.is_online:
            return Response({"message": "Executive is offline"}, status=status.HTTP_400_BAD_REQUEST)
        if executive.is_banned:
            return Response({"message": "Executive is banned"}, status=status.HTTP_403_FORBIDDEN)
        if executive.is_suspended:
            return Response({"message": "Executive is suspended"}, status=status.HTTP_403_FORBIDDEN)
        if executive.on_call:
            return Response({"message": "Executive is on another call"}, status=status.HTTP_400_BAD_REQUEST)
        return None

    def send_incoming_call_notification(self, executive_id, call_history, caller):
        """
        Send a WebSocket notification to the executive's private channel group.

        IMPORTANT: The group name MUST match the group the ExecutivesConsumer joins.
        ExecutivesConsumer uses: f"executive_{self.executive_id}" where self.executive_id
        is the executive's string code (e.g. "EXE001"), NOT the integer DB pk.
        """
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.error("[CALLS] channel_layer is None — CHANNEL_LAYERS is not configured correctly!")
                return

            # ✅ FIX (Bug 3): Use executive.executive_id (string code) not integer executive_id
            # so the group name matches what ExecutivesConsumer joins on connect.
            executive = get_object_or_404(Executive, id=executive_id)
            group_name = f"executive_{executive.executive_id}"

            # ✅ FIX (Bug 4): Guard against start_time being None
            timestamp = (
                call_history.start_time.isoformat()
                if call_history.start_time
                else timezone.now().isoformat()
            )

            payload = {
                "type": "incoming_call",
                "call_id": call_history.id,
                "channel_name": call_history.channel_name,
                "caller_name": getattr(caller, "name", "Unknown"),
                "caller_uid": call_history.uid,
                "executive_token": call_history.executive_token,
                "callee_uid": call_history.callee_uid,
                "timestamp": timestamp,
                "coins_per_second": call_history.coins_per_second,
                "amount_per_min": str(call_history.amount_per_min),
            }

            logger.info(
                "[CALLS] Sending incoming_call WebSocket notification → group=%s | call_id=%s",
                group_name, call_history.id
            )

            async_to_sync(channel_layer.group_send)(group_name, payload)

            logger.info(
                "[CALLS] incoming_call WebSocket notification delivered successfully → group=%s",
                group_name
            )

        except Exception as exc:
            logger.error(
                "[CALLS] WebSocket notification FAILED for call_id=%s: %s",
                call_history.id, exc, exc_info=True
            )

    @staticmethod
    def mark_call_as_missed(call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, status="ringing")
            call.status = "missed"
            call.is_active = False
            call.end_time = timezone.now()
            call.save(update_fields=["status", "is_active", "end_time"])

            call.executive.on_call = False
            call.executive.save(update_fields=["on_call"])

            # ✅ FIX: Use executive.executive_id (string code) to match ExecutivesConsumer group name
            exec_group = f"executive_{call.executive.executive_id}"
            user_group = f"user_{call.user.id}"

            channel_layer = get_channel_layer()
            if channel_layer:
                try:
                    async_to_sync(channel_layer.group_send)(
                        exec_group,
                        {"type": "call_missed", "call_id": call_id}
                    )
                    async_to_sync(channel_layer.group_send)(
                        user_group,
                        {"type": "call_missed", "call_id": call_id}
                    )
                    logger.info("[CALLS] call_missed sent to exec_group=%s and user_group=%s",
                                exec_group, user_group)
                except Exception as exc:
                    logger.error("[CALLS] Failed to send call_missed WS notification: %s", exc, exc_info=True)
            else:
                logger.error("[CALLS] channel_layer is None — cannot send call_missed notification")

        except AgoraCallHistory.DoesNotExist:
            pass
        except Exception as exc:
            logger.error("[CALLS] Error in mark_call_as_missed for call_id=%s: %s", call_id, exc, exc_info=True)


class MarkJoinedView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, channel_name):
        try:
            call = AgoraCallHistory.objects.get(channel_name=channel_name, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"message": "Active call not found"}, status=404)

        if isinstance(request.user, Executive):
            party = "executive"
        elif isinstance(request.user, UserProfile):
            party = "user"
        else:
            party = None

        call.mark_joined(party=party)
        return Response({"ok": True})


# Agora Notification Center (NCS) event codes for the Channel Event
# Notification product (productId=4). Confirm this list against the
# project's Agora Console -> Notifications setup before relying on it —
# Agora has revised these codes across product/API versions.
AGORA_JOIN_EVENT_TYPES = {103, 105, 107}   # broadcaster/audience/communication-mode user joined
AGORA_LEAVE_EVENT_TYPES = {102, 104, 106, 108}  # channel destroyed, broadcaster/audience/communication-mode user left


def _verify_agora_signature(request):
    """
    Verifies an inbound Agora NCS callback against AGORA_WEBHOOK_SECRET using
    HMAC-SHA256 over the raw request body, checked against the
    Agora-Signature-V2 header (confirmed via this project's live traffic —
    Agora also sends a legacy SHA-1 'Agora-Signature' header we don't use).
    """
    secret = getattr(settings, "AGORA_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning(
            "[AGORA WEBHOOK] AGORA_WEBHOOK_SECRET is not set — skipping "
            "signature verification. This must never be empty in production."
        )
        return True

    signature = request.META.get("HTTP_AGORA_SIGNATURE_V2", "")
    if not signature:
        return False

    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class AgoraWebhookView(APIView):
    """
    Receives Agora Notification Center (NCS) event callbacks. See
    AGORA_JOIN_EVENT_TYPES/AGORA_LEAVE_EVENT_TYPES above and
    _verify_agora_signature for the assumptions that need confirming against
    this project's live Agora Console configuration.
    """

    authentication_classes = []           # webhook comes from Agora, not our own auth
    permission_classes = [IsAuthenticatedOrService]

    def get(self, request):
        # Agora's Console hits the callback URL with a GET when it's first
        # registered, to confirm the endpoint is reachable.
        return Response({"ok": True})

    def post(self, request):
        if not _verify_agora_signature(request):
            logger.warning("[AGORA WEBHOOK] Signature verification failed.")
            return Response({"detail": "Invalid signature."}, status=status.HTTP_403_FORBIDDEN)

        s = WebhookSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = s.validated_data

        notice_id = payload["noticeId"]
        event_type = payload["eventType"]
        notify_ms = payload["notifyMs"]
        event_payload = payload["payload"]
        channel = event_payload["channelName"]
        event_uid = str(event_payload.get("uid", ""))
        reason = event_payload.get("reason")

        notify_at = dt.datetime.fromtimestamp(notify_ms / 1000, tz=dt.timezone.utc)
        if (timezone.now() - notify_at).total_seconds() > 300:
            logger.warning(
                "[AGORA WEBHOOK] Ignoring stale notification noticeId=%s (notifyMs=%s).",
                notice_id, notify_ms,
            )
            return Response({"ok": True})

        try:
            call = AgoraCallHistory.objects.get(channel_name=channel)
        except AgoraCallHistory.DoesNotExist:
            # Might be a late callback for a deleted call; ignore
            return Response({"ok": True})

        party = None
        if event_uid == str(call.uid):
            party = "user"
        elif event_uid == str(call.callee_uid):
            party = "executive"

        if event_type in AGORA_JOIN_EVENT_TYPES:
            call.mark_joined(party=party)

        elif event_type in AGORA_LEAVE_EVENT_TYPES:
            if party == "user":
                call.user_left_at = timezone.now()
            elif party == "executive":
                call.executive_left_at = timezone.now()
            if reason:
                call.hangup_reason = reason

            req_id = f"webhook:{notice_id}"
            # Bill up to Agora's own reported moment the party actually left,
            # not whenever we happened to process this webhook — this is the
            # closest thing to an exact, real-time end time available, since
            # it comes from Agora's servers rather than our own polling loop.
            call.end_call(ender="webhook", request_id=req_id, effective_end_time=notify_at)

        # You may persist heartbeat / last activity timestamp
        call.last_heartbeat = timezone.now()
        call.save(update_fields=["last_heartbeat"])
        return Response({"ok": True})

class CallJoinView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id)
            # Only allow joining if call is ringing
            if call.status not in ["pending", "ringing"]:
                return Response(
                    {"error": f"Call cannot be joined. Current status: {call.status}"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found"}, status=status.HTTP_404_NOT_FOUND)

        
        executive = request.user  
        if call.executive.id != executive.id:
            return Response(
                {"error": "Unauthorized to join this call"}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Update call to active status
        call.status = "joined"
        call.joined_at = timezone.now()
        call.is_active = True
        if not call.executive_joined_at:
            call.executive_joined_at = timezone.now()
        call.save(update_fields=["status", "joined_at", "is_active", "executive_joined_at"])

        # Notify the caller that executive has joined
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"user_{call.user.id}",
                    {
                        "type": "call_accepted",
                        "call_id": call.id,
                        "status": "active",
                        "joined_at": call.joined_at.isoformat(),
                    }
                )
            except Exception as e:
                print(f"Failed to notify caller: {e}")

        return Response({
            "id": call.id,
            "channel_name": call.channel_name,
            "status": call.status,
            "caller_uid": call.uid,
            "callee_uid": call.callee_uid,
            "token": call.executive_token,  # Executive uses executive_token
            "joined_at": call.joined_at,
        }, status=status.HTTP_200_OK)


class RejectCallViewUser(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already inactive"}, status=404)

        call.status = "missed"
        call.is_active = False
        call.end_time = timezone.now()
        call.ended_by = "user"
        call.save(update_fields=["status", "is_active", "end_time", "ended_by"])

        if call.executive:
            call.executive.on_call = False
            call.executive.save(update_fields=["on_call"])

        return Response({
            "ok": True,
            "message": "Call rejected by user",
            "call_id": call.id,
            "status": call.status
        })


class RejectCallViewExecutive(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already inactive"}, status=404)

        call.status = "rejected"
        call.is_active = False
        call.end_time = timezone.now()
        call.ended_by = "executive"
        call.save(update_fields=["status", "is_active", "end_time", "ended_by"])

        if call.executive:
            call.executive.on_call = False
            call.executive.save(update_fields=["on_call"])

        return Response({
            "ok": True,
            "message": "Call rejected by executive",
            "call_id": call.id,
            "status": call.status
        })


# class EndCallView(APIView):
#     permission_classes = [permissions.IsAuthenticated]

#     def post(self, request, call_id):
#         try:
#             call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
#         except AgoraCallHistory.DoesNotExist:
#             return Response({"error": "Call not found or already ended"}, status=404)

#         call.end_call(ender="client")
#         return Response({"ok": True, "message": "Call ended"})

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

class CallHistoryListAPIView(APIView):
    permission_classes = [IsAdminUser]  
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomCallPagination

    def get(self, request):
        status_filter = request.query_params.get("status")  
        queryset = AgoraCallHistory.objects.all().order_by("-start_time")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = CallHistorySerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)
    

class UserCallHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomCallPagination

    def get(self, request):
        user = request.user
        status_filter = request.query_params.get("status")  

        queryset = AgoraCallHistory.objects.filter(user=user).order_by("-start_time")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = CallHistorySerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)



class ExecutiveCallHistoryListAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = CustomCallPagination

    def get(self, request):
        executive = request.user  

        status_filter = request.query_params.get("status")
        queryset = AgoraCallHistory.objects.filter(executive=executive).order_by("-start_time")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = CallHistorySerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)


class RecentExecutiveCallsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [ExecutiveTokenAuthentication]  

    def get(self, request, executive_id):
        executive = get_object_or_404(Executive, id=executive_id)

        pending_calls = AgoraCallHistory.objects.filter(
            executive=executive,
            status="ringing"
        ).order_by("-start_time").first()

        serializer = CallHistorySerializer(pending_calls)
        return Response({
            "executive": executive.name,
            "pending_calls": serializer.data
        }, status=status.HTTP_200_OK)


class UserEndCallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):
        with transaction.atomic():
            try:
                call = AgoraCallHistory.objects.select_for_update().get(id=call_id)
            except AgoraCallHistory.DoesNotExist:
                return Response({"error": "Call not found or already ended"}, status=404)

            if call.status in ["ended", "missed", "cancelled", "rejected"]:
                return Response({
                    "ok": True,
                    "message": f"Call already ended by {call.ended_by or 'system'}",
                    "coins_deducted": getattr(call, "coins_deducted", 0),
                    "executive_earnings": float(getattr(call, "executive_earnings", 0.0)),
                    "duration_seconds": getattr(call, "duration_seconds", 0)
                })

            # Get user coin balance
            try:
                user_balance = call.user.stats.coin_balance
            except UserStats.DoesNotExist:
                user_balance = 0

            if user_balance <= 0:
                ender = "system"
                reason = "Insufficient balance, call ended automatically"
                call.hangup_reason = "insufficient_balance"
            else:
                ender = "user"
                reason = "Call ended by user"
                call.hangup_reason = "user_ended"

            call.user_left_at = timezone.now()
            call.end_call(ender=ender)

        # Notify after transaction commits ensuring DB updates are visible
        self.notify_end_call(call, reason)

        return Response({
            "ok": True,
            "message": reason,
            "coins_deducted": getattr(call, "coins_deducted", 0),
            "executive_earnings": float(getattr(call, "executive_earnings", 0.0)),
            "duration_seconds": getattr(call, "duration_seconds", 0)
        })


    def notify_end_call(self, call, reason):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                # Group names MUST match what UsersConsumer/ExecutivesConsumer join on connect:
                # user_{user.id} (numeric pk) and executive_{executive.executive_id} (string code).
                for group_name in [f"user_{call.user_id}", f"executive_{call.executive.executive_id}"]:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'call_ended',
                            'call_id': call.id,
                            'reason': reason,
                            'ended_by': call.ended_by,
                            'coins_deducted': call.coins_deducted,
                            'executive_earnings': float(call.executive_earnings),
                            'duration_seconds': call.duration_seconds
                        }
                    )
        except Exception as exc:
            logger.error("[CALLS] UserEndCallView.notify_end_call failed: %s", exc, exc_info=True)



class ExecutiveEndCallView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [ExecutiveTokenAuthentication]

    def post(self, request, call_id):
        with transaction.atomic():
            try:
                call = AgoraCallHistory.objects.select_for_update().get(id=call_id)
            except AgoraCallHistory.DoesNotExist:
                return Response({"error": "Call not found or already ended"}, status=404)

            if call.status in ["ended", "missed", "cancelled", "rejected"]:
                return Response({
                    "ok": True,
                    "message": f"Call already ended by {call.ended_by or 'system'}",
                    "coins_deducted": getattr(call, "coins_deducted", 0),
                    "executive_earnings": float(getattr(call, "executive_earnings", 0.0)),
                    "duration_seconds": getattr(call, "duration_seconds", 0)
                })

            call.executive_left_at = timezone.now()
            call.hangup_reason = "executive_ended"
            call.end_call(ender="executive")
            reason = "Call ended by executive"

        # Send WebSocket notification
        self.notify_end_call(call, reason)

        return Response({
            "ok": True,
            "message": reason,
            "coins_deducted": getattr(call, "coins_deducted", 0),
            "executive_earnings": float(getattr(call, "executive_earnings", 0.0)),
            "duration_seconds": getattr(call, "duration_seconds", 0)
        })

    def notify_end_call(self, call, reason):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                for group_name in [f"user_{call.user_id}", f"executive_{call.executive.executive_id}"]:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'call_ended',
                            'call_id': call.id,
                            'reason': reason,
                            'ended_by': call.ended_by,
                            'coins_deducted': call.coins_deducted,
                            'executive_earnings': float(call.executive_earnings),
                            'duration_seconds': call.duration_seconds
                        }
                    )
        except Exception as exc:
            logger.error("[CALLS] ExecutiveEndCallView.notify_end_call failed: %s", exc, exc_info=True)


class AdminExecutiveCallHistoryAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    pagination_class = CustomCallPagination

    def get(self, request, executive_id):
        try:
            executive = Executive.objects.get(id=executive_id)
        except Executive.DoesNotExist:
            return Response(
                {"error": "Executive not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        status_filter = request.query_params.get("status")
        queryset = AgoraCallHistory.objects.filter(executive=executive).order_by("-start_time")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = CallHistorySerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)
    
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from .models import AgoraCallHistory
from users.models import UserProfile
from .serializers import CallHistorySerializer
from .pagination import CustomCallPagination  # adjust import path if needed


class AdminUserCallHistoryAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomCallPagination

    def get(self, request, user_id):
        try:
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        status_filter = request.query_params.get("status")
        queryset = AgoraCallHistory.objects.filter(user=user).order_by("-start_time")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = CallHistorySerializer(paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)

from rest_framework.exceptions import NotFound
from django.db.models import Sum, Count, Q

class CallDetailAPIView(generics.RetrieveAPIView):
    queryset = AgoraCallHistory.objects.select_related("user", "executive").all()
    serializer_class = AgoraCallHistorySerializer
    permission_classes = [permissions.AllowAny]  

    def get(self, request, *args, **kwargs):
        call_id = kwargs.get("pk")
        try:
            call = self.get_queryset().get(id=call_id)
        except AgoraCallHistory.DoesNotExist:
            raise NotFound("Call not found.")

        serializer = self.get_serializer(call)
        return Response(serializer.data)
    

class CallAnalyticsView(APIView):
    permission_classes = [IsAdminUser]  
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            # Timezone-aware local midnight for accurate 'today' filtering
            local_now = timezone.localtime(timezone.now())
            today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Single robust DB query via aggregation and conditional counting/summing
            analytics = AgoraCallHistory.objects.aggregate(
                on_call_count=Count('id', filter=Q(status='joined')),
                total_calls=Count('id', filter=Q(status='ended', duration_seconds__gt=0)),
                today_calls=Count('id', filter=Q(status='ended', duration_seconds__gt=0, start_time__gte=today_start)),
                total_talk_time_sec=Sum('duration_seconds', filter=Q(status='ended', duration_seconds__gt=0)),
                today_talk_time_sec=Sum('duration_seconds', filter=Q(status='ended', duration_seconds__gt=0, start_time__gte=today_start)),
                total_missed_calls=Count('id', filter=Q(status='missed')),
                today_missed_calls=Count('id', filter=Q(status='missed', start_time__gte=today_start)),
            )

            total_talk_time_sec = analytics['total_talk_time_sec'] or 0
            today_talk_time_sec = analytics['today_talk_time_sec'] or 0
            
            total_calls = analytics['total_calls'] or 0
            total_missed_calls = analytics['total_missed_calls'] or 0
            
            # Calculate total incoming calls (answered + missed)
            total_incoming = total_calls + total_missed_calls
            
            # Calculate answer rate as a percentage
            answer_rate = 0.0
            if total_incoming > 0:
                answer_rate = round((total_calls / total_incoming) * 100, 2)

            data = {
                "on_call_count": analytics['on_call_count'] or 0,
                "total_calls": total_calls,
                "today_calls": analytics['today_calls'] or 0,
                "total_talk_time_seconds": total_talk_time_sec,
                "total_talk_time_minutes": round(total_talk_time_sec / 60, 2),
                "today_talk_time_seconds": today_talk_time_sec,
                "today_talk_time_minutes": round(today_talk_time_sec / 60, 2),
                "total_missed_calls": total_missed_calls,
                "today_missed_calls": analytics['today_missed_calls'] or 0,
                "answer_rate_percentage": answer_rate
            }

            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class LeaveJoinedCallsView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.data.get("user_id")
        executive_id = request.data.get("executive_id")

        if not user_id and not executive_id:
            return Response({"error": "Provide at least user_id or executive_id."}, status=400)

        # Filter calls with status 'joined'
        active_calls = AgoraCallHistory.objects.filter(status="joined")
        if user_id:
            active_calls = active_calls.filter(user_id=user_id)
        if executive_id:
            active_calls = active_calls.filter(executive_id=executive_id)

        if not active_calls.exists():
            return Response({"message": "No joined calls found for the provided IDs."}, status=200)

        ended_calls = []
        for call in active_calls:
            call.end_call(ender="system")
            reason = "Call ended by system via LeaveJoinedCalls API"
            self.notify_end_call(call, reason)
            ended_calls.append(call.id)

        return Response({
            "ok": True,
            "message": f"Ended {len(ended_calls)} joined calls.",
            "ended_call_ids": ended_calls
        })

    def notify_end_call(self, call, reason):
        """
        Send WebSocket updates to both user and executive clients
        to indicate the call has ended.
        """
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                for group_name in [f"user_client_{call.user_id}", f"user_executive_{call.executive_id}"]:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            "type": "call_ended",
                            "call_id": call.id,
                            "reason": reason,
                            "ended_by": call.ended_by,
                            "coins_deducted": call.coins_deducted,
                            "executive_earnings": float(call.executive_earnings),
                            "duration_seconds": call.duration_seconds,
                        }
                    )
        except Exception as e:
            print(f"WebSocket notification failed: {e}")

from agora_token_builder import RtcTokenBuilder
import random
import time

class GenerateMonitorTokenView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(
                id=call_id, 
                status="joined", 
                is_active=True
            )
            
            app_id = settings.AGORA_APP_ID
            app_certificate = settings.AGORA_APP_CERTIFICATE
            
            monitor_uid = random.randint(100000, 999999)
            expiration_time = int(time.time()) + 86400  # 24 hours
            
            ROLE_SUBSCRIBER = 2  # 1 = Publisher, 2 = Subscriber
            
            monitor_token = RtcTokenBuilder.buildTokenWithUid(
                app_id,
                app_certificate,
                call.channel_name,
                monitor_uid,
                ROLE_SUBSCRIBER,
                expiration_time
            )
            
            # Update only necessary fields
            call.monitor_uid = monitor_uid
            call.monitor_token = monitor_token
            call.is_monitored = True
            call.save()
            
            return Response({
                'success': True,
                'channel_name': call.channel_name,
                'monitor_token': monitor_token,
                'monitor_uid': monitor_uid,
                'app_id': app_id,
                'user_uid': call.uid,
                'executive_uid': call.callee_uid,
                'participants': {
                    'user': {
                        'uid': call.uid,
                        'name': call.user.user_id
                    },
                    'executive': {
                        'uid': call.callee_uid,
                        'name': call.executive.executive_id
                    }
                },
                'call_info': {
                    'start_time': call.start_time,
                    'joined_at': call.joined_at,
                    'duration_seconds': call.duration_seconds
                }
            }, status=status.HTTP_200_OK)
            
        except AgoraCallHistory.DoesNotExist:
            return Response({
                'success': False, 
                'error': 'Call not found or not active'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            return Response({
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class StopMonitoringView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id)
            call.is_monitored = False
            call.monitor_uid = None
            call.monitor_token = None
            call.save()
            
            return Response({
                'success': True,
                'message': 'Monitoring stopped'
            }, status=status.HTTP_200_OK)
            
        except AgoraCallHistory.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Call not found'
            }, status=status.HTTP_404_NOT_FOUND)


class OngoingCallsView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        ongoing_calls = AgoraCallHistory.objects.filter(
            status="joined",
            is_active=True
        ).select_related('user', 'executive').order_by('-joined_at')

        serializer = OngoingCallHistorySerializer(ongoing_calls, many=True)
        return Response({
            'success': True,
            'count': ongoing_calls.count(),
            'calls': serializer.data
        }, status=status.HTTP_200_OK)


class TerminateCallView(APIView):
    """Admin-only: force-end a stuck/ongoing call (e.g. a call that never
    received an end signal because the app crashed or lost network)."""
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request, call_id):
        with transaction.atomic():
            try:
                call = AgoraCallHistory.objects.select_for_update().get(id=call_id)
            except AgoraCallHistory.DoesNotExist:
                return Response({"error": "Call not found"}, status=status.HTTP_404_NOT_FOUND)

            if call.status in ["ended", "missed", "cancelled", "rejected"]:
                return Response({
                    "ok": True,
                    "message": f"Call already ended by {call.ended_by or 'system'}",
                    "coins_deducted": getattr(call, "coins_deducted", 0),
                    "executive_earnings": float(getattr(call, "executive_earnings", 0.0)),
                    "duration_seconds": getattr(call, "duration_seconds", 0)
                })

            call.end_call(ender="admin")
            reason = "Call terminated by admin"

        self.notify_end_call(call, reason)

        return Response({
            "ok": True,
            "message": reason,
            "coins_deducted": getattr(call, "coins_deducted", 0),
            "executive_earnings": float(getattr(call, "executive_earnings", 0.0)),
            "duration_seconds": getattr(call, "duration_seconds", 0)
        }, status=status.HTTP_200_OK)

    def notify_end_call(self, call, reason):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                for group_name in [f"user_{call.user_id}", f"executive_{call.executive.executive_id}"]:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'call_ended',
                            'call_id': call.id,
                            'reason': reason,
                            'ended_by': call.ended_by,
                            'coins_deducted': call.coins_deducted,
                            'executive_earnings': float(call.executive_earnings),
                            'duration_seconds': call.duration_seconds
                        }
                    )
        except Exception as exc:
            logger.error("[CALLS] TerminateCallView.notify_end_call failed: %s", exc, exc_info=True)
