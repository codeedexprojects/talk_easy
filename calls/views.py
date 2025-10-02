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
from executives.authentication import ExecutiveTokenAuthentication
from rest_framework.permissions import IsAuthenticated
from executives.models import ExecutiveStats
from .pagination import CustomCallPagination
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAdminUser
from calls.utils import generate_agora_token
import threading
import time
from executives.models import Executive
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from users.models import UserStats

class IsAuthenticatedOrService(permissions.BasePermission):
 
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        # allow for webhook endpoint; actual verification will be inside the view
        return view.__class__.__name__ == "AgoraWebhookView"




import threading
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AgoraCallHistory
from calls.serializers import CallInitiateSerializer
from calls.utils import generate_agora_token
from executives.models import Executive, ExecutiveStats
from users.models import UserStats


class CallInitiateView(APIView):
    def post(self, request):
        serializer = CallInitiateSerializer(data=request.data)
        if serializer.is_valid():
            executive_id = serializer.validated_data['executive_id']
            channel_name = serializer.validated_data['channel_name']
            caller_uid = serializer.validated_data['caller_uid']

            # Get executive
            executive = get_object_or_404(Executive, id=executive_id)

            # Validate executive availability
            validation_error = self.validate_executive(executive)
            if validation_error:
                return validation_error

            user = request.user
            try:
                user_stats = user.stats
            except UserStats.DoesNotExist:
                return Response(
                    {"detail": "User stats not found"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if user_stats.coin_balance < 180:
                return Response(
                    {"detail": "At least 180 coins required to start a call"},
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            # Mark executive as on call
            executive.on_call = True
            executive.save(update_fields=["on_call"])

            # Generate tokens
            caller_token = generate_agora_token(channel_name, caller_uid)
            callee_uid = caller_uid + 1000
            executive_token = generate_agora_token(channel_name, callee_uid)

            # Get executive stats
            exec_stats, _ = ExecutiveStats.objects.get_or_create(executive=executive)
            rate_per_minute = exec_stats.amount_per_min
            coins_per_second = exec_stats.coins_per_second

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
                user=user,
                coins_per_second=coins_per_second,
                amount_per_min=rate_per_minute
            )

            # Send WebSocket notification
            self.send_incoming_call_notification(executive_id, call_history, user)

            # Schedule missed call check (non-Celery)
            threading.Timer(30, self.mark_call_as_missed, args=[call_history.id]).start()

            return Response({
                "id": call_history.id,
                "executive_id": executive_id,
                "channel_name": channel_name,
                "caller_uid": caller_uid,
                "token": caller_token,
                "callee_uid": callee_uid,
                "executive_token": executive_token,
                "status": "pending",
                "coins_per_second": coins_per_second,
                "amount_per_min": str(rate_per_minute)
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def validate_executive(self, executive):
        if not executive.is_online:
            return Response({"detail": "Executive is offline"}, status=status.HTTP_400_BAD_REQUEST)
        if executive.is_banned:
            return Response({"detail": "Executive is banned"}, status=status.HTTP_403_FORBIDDEN)
        if executive.is_suspended:
            return Response({"detail": "Executive is suspended"}, status=status.HTTP_403_FORBIDDEN)
        if executive.on_call:
            return Response({"detail": "Executive is on another call"}, status=status.HTTP_400_BAD_REQUEST)
        return None

    def send_incoming_call_notification(self, executive_id, call_history, caller):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"executive_{executive_id}",
                    {
                        "type": "incoming_call",
                        "call_id": call_history.id,
                        "channel_name": call_history.channel_name,
                        "caller_name": getattr(caller, "name", "Unknown"),
                        "caller_uid": call_history.uid,
                        "executive_token": call_history.executive_token,
                        "callee_uid": call_history.callee_uid,
                        "timestamp": call_history.start_time.isoformat(),
                        "coins_per_second": call_history.coins_per_second,
                        "amount_per_min": str(call_history.amount_per_min),
                    }
                )
        except Exception as e:
            print(f"WebSocket notification failed: {e}")

    @staticmethod
    def mark_call_as_missed(call_id):
        """Mark call as missed after timeout (threading version)."""
        try:
            call = AgoraCallHistory.objects.get(id=call_id, status="pending")
            call.status = "missed"
            call.is_active = False
            call.end_time = timezone.now()
            call.save(update_fields=["status", "is_active", "end_time"])

            call.executive.on_call = False
            call.executive.save(update_fields=["on_call"])

            # WebSocket notifications
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
    permission_classes = []

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already ended"}, status=404)

        #  Check if user has coins left before ending
        if call.user.coin_balance <= 0:
            call.end_call(ender="system")
            reason = "Insufficient balance, call ended automatically"
        else:
            call.end_call(ender="client")
            reason = "Call ended by user"

        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                caller_group = f"user_client_{call.user_id}"
                executive_group = f"user_executive_{call.executive_id}"
                for group_name in [caller_group, executive_group]:
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
        except Exception as e:
            print(f"WebSocket end call notification failed: {e}")

        return Response({
            "ok": True,
            "message": reason,
            "coins_deducted": call.coins_deducted,
            "executive_earnings": float(call.executive_earnings),
            "duration_seconds": call.duration_seconds
        })






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
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id)
            if call.status not in ["pending", "active"]:
                return Response({"error": "Call not active"}, status=status.HTTP_400_BAD_REQUEST)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found"}, status=status.HTTP_404_NOT_FOUND)

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
        call.is_active = True
        call.save()

        return Response({
            "id": call.id,
            "channel_name": call.channel_name,
            "status": call.status,
            "caller_uid": call.uid,
            "callee_uid": call.callee_uid,
            "token": call.token,
            "executive_token": call.executive_token,
            "joined_at": call.joined_at,
        }, status=status.HTTP_200_OK)



class RejectCallViewUser(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
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
            status="pending"
        ).order_by("-start_time")[:20]

        serializer = CallHistorySerializer(pending_calls, many=True)
        return Response({
            "executive": executive.name,
            "total_pending_calls": pending_calls.count(),
            "pending_calls": serializer.data
        }, status=status.HTTP_200_OK)
