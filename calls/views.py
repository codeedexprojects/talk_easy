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
                    {"message": "User stats not found"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if user_stats.coin_balance < 180:
                return Response(
                    {"message": "At least 180 coins required to start a call"},
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

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
            rate_per_minute = exec_stats.amount_per_min
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
                status="ringing",  # Changed from "pending" to "ringing"
                is_active=False,   # Not active until executive joins
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
                "executive_code":executive_code,
                "channel_name": channel_name,
                "caller_uid": caller_uid,
                "token": caller_token,
                "callee_uid": callee_uid,
                "executive_token": executive_token,
                "status": "ringing",
                "coins_per_second": coins_per_second,
                "amount_per_min": str(rate_per_minute)
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
        try:
            call = AgoraCallHistory.objects.get(id=call_id, status="ringing")  # Changed from "pending"
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


class MarkJoinedView(APIView):
   
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, channel_name):
        try:
            call = AgoraCallHistory.objects.get(channel_name=channel_name, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"message": "Active call not found"}, status=404)
        call.mark_joined()
        return Response({"ok": True})


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
            # Only allow joining if call is ringing
            if call.status != "ringing":
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
        call.status = "active"
        call.joined_at = timezone.now()
        call.is_active = True
        call.save(update_fields=["status", "joined_at", "is_active"])

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
        ).order_by("-start_time").first()

        serializer = CallHistorySerializer(pending_calls)
        return Response({
            "executive": executive.name,
            "pending_calls": serializer.data
        }, status=status.HTTP_200_OK)


class UserEndCallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already ended"}, status=404)

        # Get user coin balance
        try:
            user_balance = call.user.stats.coin_balance
        except UserStats.DoesNotExist:
            user_balance = 0

        if user_balance <= 0:
            call.end_call(ender="system")
            reason = "Insufficient balance, call ended automatically"
        else:
            call.end_call(ender="user")
            reason = "Call ended by user"

        # Send WebSocket notification
        self.notify_end_call(call, reason)

        return Response({
            "ok": True,
            "message": reason,
            "coins_deducted": call.coins_deducted,
            "executive_earnings": float(call.executive_earnings),
            "duration_seconds": call.duration_seconds
        })


    def notify_end_call(self, call, reason):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                for group_name in [f"user_client_{call.user_id}", f"user_executive_{call.executive_id}"]:
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
            print(f"WebSocket notification failed: {e}")



class ExecutiveEndCallView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [ExecutiveTokenAuthentication]

    def post(self, request, call_id):
        try:
            call = AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return Response({"error": "Call not found or already ended"}, status=404)

        call.end_call(ender="executive")
        reason = "Call ended by executive"

        # Send WebSocket notification
        self.notify_end_call(call, reason)

        return Response({
            "ok": True,
            "message": reason,
            "coins_deducted": call.coins_deducted,
            "executive_earnings": float(call.executive_earnings),
            "duration_seconds": call.duration_seconds
        })

    def notify_end_call(self, call, reason):
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                for group_name in [f"user_client_{call.user_id}", f"user_executive_{call.executive_id}"]:
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
            print(f"WebSocket notification failed: {e}")


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
from django.db.models import Sum

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
            today = timezone.now().date()
            
            on_call_count = AgoraCallHistory.objects.filter(status='joined').count()

            total_calls = AgoraCallHistory.objects.filter(status='ended').count()

            today_calls = AgoraCallHistory.objects.filter(
                status='ended', start_time__date=today
            ).count()

            total_talk_time_sec = AgoraCallHistory.objects.filter(status='ended').aggregate(
                total_duration=Sum('duration_seconds')
            )['total_duration'] or 0

            today_talk_time_sec = AgoraCallHistory.objects.filter(
                status='ended', start_time__date=today
            ).aggregate(total_duration=Sum('duration_seconds'))['total_duration'] or 0

            total_talk_time_min = round(total_talk_time_sec / 60, 2)
            today_talk_time_min = round(today_talk_time_sec / 60, 2)
            total_missed_calls = AgoraCallHistory.objects.filter(status='missed').count()
            today_missed_calls = AgoraCallHistory.objects.filter(
                status='missed', start_time__date=today
            ).count()

            data = {
                "on_call_count": on_call_count,
                "total_calls": total_calls,
                "today_calls": today_calls,
                "total_talk_time_seconds": total_talk_time_sec,
                "total_talk_time_minutes": total_talk_time_min,
                "today_talk_time_seconds": today_talk_time_sec,
                "today_talk_time_minutes": today_talk_time_min,
                "total_missed_calls": total_missed_calls,
                "today_missed_calls": today_missed_calls
            }

            return Response(data, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        

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


class OngoingCallsView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]

    def get(self, request):
        ongoing_calls = AgoraCallHistory.objects.filter(status="joined", is_active=True)
        serializer = AgoraCallHistorySerializer(ongoing_calls, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)