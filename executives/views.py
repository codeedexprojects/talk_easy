# views.py
from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import Max
from .models import Executive, ExecutiveStats
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import Coalesce
from decimal import Decimal
import logging
from .serializers import *

logger = logging.getLogger(__name__)
import re
from django.contrib.auth import authenticate
import random
from executives.utils import send_otp
from rest_framework.views import APIView
from executives.models import *
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from executives.permissions import IsAdminUser
# For admin-specific views
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from executives.authentication import ExecutiveTokenAuthentication
from executives.utils import send_otp, is_test_number
from notifications.utils import (
    TOPIC_ALL_EXECUTIVES,
    TOPIC_ALL_MEMBERS,
    subscribe_token_to_topic,
    unsubscribe_token_from_topic,
)
import uuid
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync



class LanguageListCreateView(generics.ListCreateAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

class LanguageListView(generics.ListAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = []

class LanguageDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]


def generate_executive_tokens(executive):
    refresh = RefreshToken.for_user(executive) 
    ExecutiveToken.objects.create(executive=executive, refresh_token=str(refresh))
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

def generate_executive_id():
    last_id = Executive.objects.aggregate(max_id=Max('executive_id'))['max_id']
    if last_id:
        number = int(re.sub(r'\D', '', last_id)) + 1
    else:
        number = 1
    return f"TEY{str(number).zfill(4)}"  # TEY00001


from rest_framework.exceptions import ValidationError

class RegisterExecutiveView(generics.CreateAPIView):
    """
    LEGACY / CURRENTLY LIVE endpoint — untouched, still used by the app in production.
    Creates the executive record only. No OTP is sent here; OTP happens at login
    (see legacy ExecutiveLoginView / ExecutiveVerifyOTPView below).
    """
    permission_classes = []
    queryset = Executive.objects.all()
    serializer_class = ExecutiveSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['executive_id'] = generate_executive_id()

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            error_messages = []
            for field, messages in e.detail.items():
                error_messages.append(f"{' '.join(messages)}")

            return Response(
                {
                    "message": " ".join(error_messages)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        executive = serializer.save()
        ExecutiveStats.objects.create(executive=executive)

        return Response(
            {
                "message": "Registration completed, the account will be verified within 24 hours.",
                "executive": ExecutiveSerializer(executive).data
            },
            status=status.HTTP_201_CREATED
        )


from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import check_password
from django.core.cache import cache


class ExecutiveLoginView(APIView):
    """
    LEGACY / CURRENTLY LIVE endpoint — untouched, still used by the app in production.
    mobile_number + password -> OTP sent -> ExecutiveVerifyOTPView completes login.
    """
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        password = request.data.get("password")

        if not mobile_number or not password:
            return Response(
                {"message": "Mobile number and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Test login shortcut (bypass password check)
        if is_test_number(mobile_number):
            otp = "123456"  # fixed OTP for testing
            executive, created = Executive.objects.get_or_create(
                mobile_number=mobile_number,
                defaults={"name": "Test Executive", "is_verified": True}
            )
            executive.otp = otp
            executive.is_verified = True
            executive.save(update_fields=["otp", "is_verified"])

            return Response({
                "message": "Test login: OTP sent successfully (static for testing).",
                "status": True,
                "otp": otp
            }, status=status.HTTP_200_OK)

        # Regular flow
        try:
            executive = Executive.objects.get(mobile_number=mobile_number)
        except Executive.DoesNotExist:
            return Response({"message": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)

        if not check_password(password, executive.password):
            return Response({"message": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED)

        if executive.is_suspended or executive.is_banned:
            return Response(
                {"message": "Your account is suspended or banned. Contact admin."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not executive.is_verified:
            return Response(
                {"message": "Your account is not verified by admin yet."},
                status=status.HTTP_403_FORBIDDEN
            )

        otp = str(random.randint(100000, 999999))
        executive.otp = otp
        executive.is_verified = True
        executive.save(update_fields=["otp", "is_verified"])

        if not send_otp(mobile_number, otp):
            return Response({"message": "Failed to send OTP"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "message": "Password verified. OTP sent to your mobile. Please verify to complete login.",
            "status": True,
            "otp": otp
        }, status=status.HTTP_200_OK)


class ExecutiveVerifyOTPView(APIView):
    """
    LEGACY / CURRENTLY LIVE endpoint — untouched, still used by the app in production.
    Second step of ExecutiveLoginView above.
    """
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        otp = request.data.get("otp")
        fcm_token = request.data.get("fcm_token")

        try:
            executive = Executive.objects.get(mobile_number=mobile_number)
        except Executive.DoesNotExist:
            return Response(
                {"message": "Executive not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        if is_test_number(mobile_number) and otp == "123456":
            ExecutiveToken.objects.filter(executive=executive, revoked=False).update(
                revoked=True, revoked_at=timezone.now()
            )

            access_token = str(uuid.uuid4())
            refresh_token = str(uuid.uuid4())
            expires_at = timezone.now() + timedelta(days=7)

            new_token = ExecutiveToken.objects.create(
                executive=executive,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at
            )

            executive.online = True
            executive.is_logged_out = False
            executive.is_verified = True

            if fcm_token and fcm_token != executive.fcm_token:
                if executive.fcm_token:
                    unsubscribe_token_from_topic(executive.fcm_token, TOPIC_ALL_EXECUTIVES)
                    unsubscribe_token_from_topic(executive.fcm_token, TOPIC_ALL_MEMBERS)
                executive.fcm_token = fcm_token
                subscribe_token_to_topic(fcm_token, TOPIC_ALL_EXECUTIVES)
                subscribe_token_to_topic(fcm_token, TOPIC_ALL_MEMBERS)
            executive.save()

            return Response({
                "message": "Test login successful (bypassed OTP verification).",
                "executive_id": executive.executive_id,
                "id": executive.id,
                "fcm_token": executive.fcm_token,
                "name": executive.name,
                "access_token": new_token.access_token,
                "refresh_token": new_token.refresh_token,
                "expires_at": new_token.expires_at
            }, status=status.HTTP_200_OK)

        if not executive.otp or str(executive.otp) != str(otp):
            return Response(
                {"message": "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST
            )

        ExecutiveToken.objects.filter(executive=executive, revoked=False).update(
            revoked=True, revoked_at=timezone.now()
        )

        access_token = str(uuid.uuid4())
        refresh_token = str(uuid.uuid4())
        expires_at = timezone.now() + timedelta(days=7)

        new_token = ExecutiveToken.objects.create(
            executive=executive,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at
        )

        executive.otp = None
        executive.online = True
        executive.is_logged_out = False
        executive.is_verified = True

        if fcm_token and fcm_token != executive.fcm_token:
            if executive.fcm_token:
                unsubscribe_token_from_topic(executive.fcm_token, TOPIC_ALL_EXECUTIVES)
                unsubscribe_token_from_topic(executive.fcm_token, TOPIC_ALL_MEMBERS)
            executive.fcm_token = fcm_token
            subscribe_token_to_topic(fcm_token, TOPIC_ALL_EXECUTIVES)
            subscribe_token_to_topic(fcm_token, TOPIC_ALL_MEMBERS)

        executive.save()

        return Response({
            "message": "OTP verified successfully",
            "executive_id": executive.executive_id,
            "id": executive.id,
            "fcm_token": executive.fcm_token,
            "name": executive.name,
            "access_token": new_token.access_token,
            "refresh_token": new_token.refresh_token,
            "expires_at": new_token.expires_at
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# NEW (v2) executive auth flow — separate endpoints, does not
# touch the legacy ones above. OTP moves to registration; login
# becomes mobile_number + password only. Switch the app over to
# these once the new build is ready to go live.
# ─────────────────────────────────────────────────────────────

def _issue_executive_tokens(executive, fcm_token):
    ExecutiveToken.objects.filter(executive=executive, revoked=False).update(
        revoked=True, revoked_at=timezone.now()
    )

    new_token = ExecutiveToken.objects.create(
        executive=executive,
        access_token=str(uuid.uuid4()),
        refresh_token=str(uuid.uuid4()),
        expires_at=timezone.now() + timedelta(days=7)
    )

    executive.online = True
    executive.is_logged_out = False

    if fcm_token and fcm_token != executive.fcm_token:
        if executive.fcm_token:
            unsubscribe_token_from_topic(executive.fcm_token, TOPIC_ALL_EXECUTIVES)
            unsubscribe_token_from_topic(executive.fcm_token, TOPIC_ALL_MEMBERS)
        executive.fcm_token = fcm_token
        subscribe_token_to_topic(fcm_token, TOPIC_ALL_EXECUTIVES)
        subscribe_token_to_topic(fcm_token, TOPIC_ALL_MEMBERS)

    executive.save()
    return new_token


class SendRegistrationOTPView(APIView):
    """
    NEW v2 step 1: request an OTP for a mobile number BEFORE any account exists.
    Follow up with RegisterExecutiveV2View, passing the same mobile_number + otp
    along with the rest of the registration data.
    """
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        if not mobile_number:
            return Response({"message": "Mobile number is required."}, status=status.HTTP_400_BAD_REQUEST)

        if Executive.objects.filter(mobile_number=mobile_number).exists():
            return Response(
                {"message": "This mobile number is already registered."},
                status=status.HTTP_400_BAD_REQUEST
            )

        ExecutivePendingRegistrationOTP.objects.filter(mobile_number=mobile_number).delete()

        if is_test_number(mobile_number):
            otp = "123456"
            otp_sent = True
        else:
            otp = str(random.randint(100000, 999999))
            otp_sent = send_otp(mobile_number, otp)

        ExecutivePendingRegistrationOTP.objects.create(
            mobile_number=mobile_number,
            otp=otp,
            expires_at=timezone.now() + timedelta(minutes=10)
        )

        message = (
            "OTP sent to your mobile number."
            if otp_sent else
            "We couldn't send the OTP SMS right now. Please try again shortly."
        )

        return Response({"message": message, "otp_sent": otp_sent}, status=status.HTTP_200_OK)


class RegisterExecutiveV2View(generics.CreateAPIView):
    """
    NEW v2 step 2: creates the executive ONLY if a valid, unexpired OTP was
    requested for this mobile_number via SendRegistrationOTPView. No account
    is created for an invalid/expired/missing OTP.
    """
    permission_classes = []
    queryset = Executive.objects.all()
    serializer_class = ExecutiveSerializer

    def create(self, request, *args, **kwargs):
        mobile_number = request.data.get("mobile_number")
        otp = request.data.get("otp")

        if not mobile_number or not otp:
            return Response(
                {"message": "Mobile number and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        pending = ExecutivePendingRegistrationOTP.objects.filter(
            mobile_number=mobile_number
        ).order_by('-created_at').first()

        if not pending or pending.is_expired() or str(pending.otp) != str(otp):
            return Response(
                {"message": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        data['executive_id'] = generate_executive_id()
        data.pop('otp', None)

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            error_messages = []
            for field, messages in e.detail.items():
                error_messages.append(f"{' '.join(messages)}")

            return Response(
                {
                    "message": " ".join(error_messages)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        executive = serializer.save()
        executive.is_phone_verified = True
        executive.save(update_fields=["is_phone_verified"])
        ExecutiveStats.objects.create(executive=executive)

        pending.delete()

        return Response(
            {
                "message": "Registration completed. Your account will be reviewed by admin.",
                "executive": ExecutiveSerializer(executive).data
            },
            status=status.HTTP_201_CREATED
        )


class ExecutiveLoginV2View(APIView):
    """
    NEW: mobile_number + password only. No OTP step — phone verification is
    checked from the registration flow (is_phone_verified) instead.
    """
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        password = request.data.get("password")
        fcm_token = request.data.get("fcm_token")

        if not mobile_number or not password:
            return Response(
                {"message": "Mobile number and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Test login shortcut (bypass password check)
        if is_test_number(mobile_number):
            executive, created = Executive.objects.get_or_create(
                mobile_number=mobile_number,
                defaults={"name": "Test Executive", "is_verified": True, "is_phone_verified": True}
            )
            if not created:
                executive.is_verified = True
                executive.is_phone_verified = True
                executive.save(update_fields=["is_verified", "is_phone_verified"])

            new_token = _issue_executive_tokens(executive, fcm_token)

            return Response({
                "message": "Test login successful.",
                "executive_id": executive.executive_id,
                "id": executive.id,
                "fcm_token": executive.fcm_token,
                "name": executive.name,
                "access_token": new_token.access_token,
                "refresh_token": new_token.refresh_token,
                "expires_at": new_token.expires_at
            }, status=status.HTTP_200_OK)

        # Regular flow
        try:
            executive = Executive.objects.get(mobile_number=mobile_number)
        except Executive.DoesNotExist:
            return Response({"message": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)

        if not check_password(password, executive.password):
            return Response({"message": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED)

        if executive.is_suspended or executive.is_banned:
            return Response(
                {"message": "Your account is suspended or banned. Contact admin."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not executive.is_phone_verified:
            return Response(
                {"message": "Please verify your mobile number with the OTP sent during registration."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not executive.is_verified:
            return Response(
                {"message": "Your account is not verified by admin yet."},
                status=status.HTTP_403_FORBIDDEN
            )

        new_token = _issue_executive_tokens(executive, fcm_token)

        return Response({
            "message": "Login successful",
            "executive_id": executive.executive_id,
            "id": executive.id,
            "fcm_token": executive.fcm_token,
            "name": executive.name,
            "access_token": new_token.access_token,
            "refresh_token": new_token.refresh_token,
            "expires_at": new_token.expires_at
        }, status=status.HTTP_200_OK)


from rest_framework.permissions import IsAuthenticated

class ExecutiveLogoutView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, executive_id):
        updated = Executive.objects.filter(id=executive_id).update(
            online=False, 
            is_logged_out=True
        )

        if updated == 0:
            return Response({"message": "Executive not found."}, status=404)

        return Response({"message": "Logout successful."}, status=200)


from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.authentication import JWTAuthentication
from accounts.pagination import CustomExecutivePagination
from rest_framework.generics import ListAPIView

class ExecutiveListAPIView(ListAPIView):
    serializer_class = ExecutiveSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomExecutivePagination

    def get_queryset(self):
        return Executive.objects.filter(is_verified=True).order_by("-id")


class ExecutiveDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication] 

    def get(self, request, id):
        executive = get_object_or_404(Executive, id=id)
        serializer = ExecutiveSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class ExecutiveUpdateByIDAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        if request.user.id != id:
            return Response({"detail": "Not authorized to access this profile."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        # Import locally to avoid circular dependencies if any
        from calls.models import AgoraCallHistory
        from users.models import Rating

        # Dynamic Aggregation for precision
        stats_data = AgoraCallHistory.objects.filter(executive=executive).aggregate(
            total_calls=Count('id'),
            completed_calls=Count('id', filter=Q(status='ended')),
            missed_calls=Count('id', filter=Q(status='missed')),
            total_duration_seconds=Coalesce(Sum('duration_seconds', filter=Q(status='ended')), 0),
            total_earnings=Coalesce(Sum('executive_earnings', filter=Q(status='ended')), Decimal('0.00'))
        )

        # earnings_today — uses ExecutiveStats which auto-resets each day
        exec_stats, _ = ExecutiveStats.objects.get_or_create(executive=executive)
        earnings_today = exec_stats.current_earnings_today  # resets to 0 if new day

        avg_rating = Rating.objects.filter(executive=executive).aggregate(
            avg_rating=Avg('rating')
        )['avg_rating'] or 0.0

        total_call_minutes = round(stats_data['total_duration_seconds'] / 60, 2)

        # Logging for debug
        logger.info(f"Aggregated stats for Executive {id}: {stats_data}, Avg Rating: {avg_rating}")

        # Basic executive data from serializer
        serializer = ExecutiveSerializer(executive)
        data = serializer.data

        # Update data with aggregated stats
        data.update({
            "total_calls": stats_data['total_calls'],
            "completed_calls": stats_data['completed_calls'],
            "missed_calls": stats_data['missed_calls'],
            "total_call_minutes": total_call_minutes,
            "total_earnings": float(stats_data['total_earnings']),
            "earnings_today": float(earnings_today),
            "average_rating": round(avg_rating, 1)
        })

        return Response(data, status=status.HTTP_200_OK)

    def put(self, request, id):
        return self.update_executive(request, id)

    def patch(self, request, id):
        return self.update_executive(request, id, partial=True)

    def update_executive(self, request, id, partial=False):
        if request.user.id != id:
            return Response({"detail": "Not authorized to update this profile."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveSerializer(executive, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    
class AdminUpdateExecutiveAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request, id):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id):
        return self.update_executive(request, id)

    def patch(self, request, id):
        return self.update_executive(request, id, partial=True)

    def delete(self, request, id):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        executive.delete()
        return Response({"detail": "Executive deleted successfully.", "status": True}, status=status.HTTP_200_OK)

    def update_executive(self, request, id, partial=False):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveSerializer(executive, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    
from users.models import UserProfile

class BlockUserAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        executive = request.user 

        try:
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        obj, created = BlockedusersByExecutive.objects.update_or_create(
            user=user,
            executive=executive,
            defaults={'is_blocked': True, 'reason': 'Blocked by executive'}
        )
        return Response(
            {"message": f"User {user_id} blocked by Executive {executive.executive_id} successfully.", "status": True},
            status=status.HTTP_200_OK
        )
    
class BlockedUsersListAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        executive = request.user  

        blocked_users = BlockedusersByExecutive.objects.filter(
            executive=executive,
            is_blocked=True
        ).select_related("user")

        data = [
            {
                "user_id": obj.user.id,
                "username": obj.user.user_id,
                "reason": obj.reason,
                "blocked_at": obj.blocked_at,
            }
            for obj in blocked_users
        ]

        return Response({"blocked_users": data}, status=status.HTTP_200_OK)


class UnblockUserAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        executive = request.user 

        try:
            blocked_entry = BlockedusersByExecutive.objects.get(user_id=user_id, executive=executive)
            blocked_entry.is_blocked = False
            blocked_entry.save(update_fields=['is_blocked'])
            return Response(
                {"message": f"User {user_id} unblocked by Executive {executive.executive_id} successfully.", "status": True},
                status=status.HTTP_200_OK
            )
        except BlockedusersByExecutive.DoesNotExist:
            return Response(
                {"message": "This user is not blocked by you.", "status": False},
                status=status.HTTP_404_NOT_FOUND
            )
        
class UpdateExecutiveStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]  
    authentication_classes = [JWTAuthentication]


    def patch(self, request, executive_id):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized.", "status": False}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=executive_id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found.", "status": False}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveStatusUpdateSerializer(executive, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()

            if executive.is_banned:
                self.force_logout(executive)

            return Response({"detail": "Executive status updated successfully.", "status": True}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def force_logout(self, executive):
        """Revoke active sessions and disconnect any live socket for a just-banned executive."""
        ExecutiveToken.objects.filter(executive=executive, revoked=False).update(
            revoked=True, revoked_at=timezone.now()
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"executive_{executive.executive_id}",
                    {"type": "force_logout", "reason": "Your account has been banned."}
                )
            except Exception as exc:
                logger.error("[BAN] Failed to send force_logout to executive_id=%s: %s", executive.executive_id, exc, exc_info=True)

class UpdateExecutiveOnlineStatusAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication] 
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        executive = request.user

        serializer = ExecutiveOnlineStatusSerializer(executive, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "detail": "Status updated successfully.",
                "status": True,
                "is_online": executive.is_online,
                "is_offline": executive.is_offline,
                "executive_id":executive.executive_id,
                "id": executive.id

            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class ExecutiveSuspendToggleView(APIView):
    authentication_classes = [JWTAuthentication]  
    permission_classes = [IsAdminUser]

    def post(self, request, id): 
        try:
            executive = Executive.objects.get(id=id) 
        except Executive.DoesNotExist:
            return Response({"error": "Executive not found"}, status=404)
        executive.is_suspended = not executive.is_suspended
        executive.save()

        status_text = "suspended" if executive.is_suspended else "unsuspended"
        return Response(
            {
                "id": executive.id,
                "name": executive.name,
                "is_suspended": executive.is_suspended,
                "message": f"Executive has been {status_text} successfully."
            },
            status=status.HTTP_200_OK
        )
    
class ExecutiveProfilePictureUploadView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication] 
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, executive_id=None):
        try:
            if executive_id:
                executive = get_object_or_404(Executive, id=executive_id)
            else:
                executive = get_object_or_404(Executive, id=request.user.id)

            if 'profile_photo' not in request.FILES:
                return Response(
                    {"error": "No profile photo provided"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            profile_picture = ExecutiveProfilePicture.objects.create(
                executive=executive,
                profile_photo=request.FILES['profile_photo'],
                status='pending'
            )

            serializer = ExecutiveProfilePictureSerializer(profile_picture, context={"request": request})

            return Response({
                "message": "Profile picture uploaded successfully. Status: Pending approval.",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)

        except Executive.DoesNotExist:
            return Response({"error": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, executive_id=None):
        try:
            if executive_id:
                executive = get_object_or_404(Executive, id=executive_id)
            else:
                executive = get_object_or_404(Executive, id=request.user.id)

            profile_picture = ExecutiveProfilePicture.objects.filter(
                executive=executive
            ).order_by('-created_at').first()
            if profile_picture:
                serializer = ExecutiveProfilePictureSerializer(profile_picture, context={"request": request})
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"message": "No profile picture found for this executive"},
                    status=status.HTTP_404_NOT_FOUND
                )

        except Executive.DoesNotExist:
            return Response({"error": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)



class ExecutiveProfilePictureStatusView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, executive_id=None):

        try:
            if executive_id:
                executive = get_object_or_404(Executive, id=executive_id)
            else:
                executive = get_object_or_404(Executive, user=request.user)

            profile_picture = ExecutiveProfilePicture.objects.filter(
                executive=executive
            ).order_by('-created_at').first()
            if profile_picture:
                return Response({
                    "status": profile_picture.status,
                    "created_at": profile_picture.created_at,
                    "updated_at": profile_picture.updated_at
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "status": "not_uploaded",
                    "message": "No profile picture uploaded yet"
                }, status=status.HTTP_200_OK)
                
        except Executive.DoesNotExist:
            return Response(
                {"error": "Executive not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
from django.db.models import Q      
class AdminProfilePictureListView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication] 
    
    def get(self, request):
        queryset = ExecutiveProfilePicture.objects.select_related('executive').all()        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)        
        executive_id = request.query_params.get('executive_id')
        if executive_id:
            queryset = queryset.filter(executive_id=executive_id)        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(executive__name__icontains=search) |
                Q(executive__email__icontains=search)
            )        
        queryset = queryset.order_by('-created_at')
        
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 20)
        
        try:
            page = int(page)
            page_size = int(page_size)
            start = (page - 1) * page_size
            end = start + page_size
            
            total_count = queryset.count()
            paginated_queryset = queryset[start:end]
            
            serializer = ExecutiveProfilePictureSerializer(
                paginated_queryset, 
                many=True, 
                context={'request': request}
            )
            
            return Response({
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size,
                "results": serializer.data
            }, status=status.HTTP_200_OK)
            
        except ValueError:
            return Response(
                {"error": "Invalid page or page_size parameter"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
class AdminProfilePictureDetailView(APIView):
    authentication_classes = [JWTAuthentication]  
    permission_classes = [IsAdminUser]    
    def get(self, request, picture_id):
        try:
            profile_picture = ExecutiveProfilePicture.objects.select_related('executive').get(id=picture_id)
            serializer = ExecutiveProfilePictureSerializer(profile_picture, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ExecutiveProfilePicture.DoesNotExist:
            return Response(
                {"error": "Profile picture not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AdminProfilePictureApproveView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]   
    def post(self, request, picture_id):
        try:
            profile_picture = ExecutiveProfilePicture.objects.get(id=picture_id)
            
            if profile_picture.status == 'approved':
                return Response(
                    {"message": "Profile picture is already approved"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            profile_picture.approve()
            
            serializer = ExecutiveProfilePictureSerializer(profile_picture, context={'request': request})
            
            return Response({
                "message": "Profile picture approved successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except ExecutiveProfilePicture.DoesNotExist:
            return Response(
                {"error": "Profile picture not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AdminProfilePictureRejectView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    
    def post(self, request, picture_id):
        serializer = AdminProfilePictureActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            profile_picture = ExecutiveProfilePicture.objects.get(id=picture_id)
            
            if profile_picture.status == 'rejected':
                return Response(
                    {"message": "Profile picture is already rejected"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            profile_picture.reject()            
            serializer_response = ExecutiveProfilePictureSerializer(profile_picture, context={'request': request})
            
            return Response({
                "message": "Profile picture rejected successfully",
                "data": serializer_response.data,
                "reason": serializer.validated_data.get('reason', '')
            }, status=status.HTTP_200_OK)
            
        except ExecutiveProfilePicture.DoesNotExist:
            return Response(
                {"error": "Profile picture not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AdminProfilePictureBulkActionView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    
    def post(self, request):
        action = request.data.get('action')
        picture_ids = request.data.get('picture_ids', [])
        reason = request.data.get('reason', '')
        
        if action not in ['approve', 'reject']:
            return Response(
                {"error": "Action must be either 'approve' or 'reject'"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not picture_ids or not isinstance(picture_ids, list):
            return Response(
                {"error": "picture_ids must be a non-empty list"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            profile_pictures = ExecutiveProfilePicture.objects.filter(id__in=picture_ids)
            
            if not profile_pictures.exists():
                return Response(
                    {"error": "No profile pictures found with provided IDs"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            updated_count = 0
            results = []
            
            for picture in profile_pictures:
                if action == 'approve' and picture.status != 'approved':
                    picture.approve()
                    updated_count += 1
                    results.append({
                        "id": picture.id,
                        "executive": picture.executive.name,
                        "status": "approved",
                        "message": "Approved successfully"
                    })
                elif action == 'reject' and picture.status != 'rejected':
                    picture.reject()
                    updated_count += 1
                    results.append({
                        "id": picture.id,
                        "executive": picture.executive.name,
                        "status": "rejected",
                        "message": "Rejected successfully",
                        "reason": reason
                    })
                else:
                    results.append({
                        "id": picture.id,
                        "executive": picture.executive.name,
                        "status": picture.status,
                        "message": f"Already {picture.status}"
                    })
            
            return Response({
                "message": f"Bulk {action} completed",
                "updated_count": updated_count,
                "total_processed": len(results),
                "results": results
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": f"An error occurred during bulk action: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminProfilePictureStatsView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    
    def get(self, request):
        total = ExecutiveProfilePicture.objects.count()
        pending = ExecutiveProfilePicture.objects.filter(status='pending').count()
        approved = ExecutiveProfilePicture.objects.filter(status='approved').count()
        rejected = ExecutiveProfilePicture.objects.filter(status='rejected').count()
        
        from django.utils import timezone
        from datetime import timedelta
        
        week_ago = timezone.now() - timedelta(days=7)
        recent = ExecutiveProfilePicture.objects.filter(created_at__gte=week_ago).count()
        
        return Response({
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "recent_submissions": recent,
            "approval_rate": round((approved / total * 100) if total > 0 else 0, 2)
        }, status=status.HTTP_200_OK)
    
class ExecutiveStatusAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        executive = request.user 
        serializer = ExecutiveDetailSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class ExecutiveStatsDetailView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication] 
    def get(self, request, id):
        executive = get_object_or_404(Executive, id=id)

        stats, _ = ExecutiveStats.objects.get_or_create(executive=executive)

        serializer = ExecutiveStatsSerializer(stats)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class BlockedUsersListByExecutiveAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  

    def get(self, request, executive_id):
        executive = get_object_or_404(Executive, id=executive_id)

        blocked_users = BlockedusersByExecutive.objects.filter(executive=executive, is_blocked=True).select_related("user")

        serializer = BlockedUserSerializer(blocked_users, many=True)
        return Response({
            "executive": executive.name,
            "total_blocked": blocked_users.count(),
            "blocked_users": serializer.data
        }, status=status.HTTP_200_OK)
    

class AllBlockedUsersListView(APIView):
    permission_classes = [IsAdminUser]  
    authentication_classes=[JWTAuthentication]

    def get(self, request):
        blocked_users = BlockedusersByExecutive.objects.filter(is_blocked=True).select_related('user', 'executive')
        serializer = BlockedUsersSerializer(blocked_users, many=True)
        return Response(serializer.data)
    

class ExecutiveSearchView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]  

    def get(self, request):
        query = request.query_params.get('query', '').strip()

        if not query:
            return Response({"error": "Please provide a search query."}, status=status.HTTP_400_BAD_REQUEST)

        executives = Executive.objects.filter(
            Q(executive_id__icontains=query) |
            Q(name__icontains=query) |
            Q(mobile_number__icontains=query) |
            Q(email_id__icontains=query) |
            Q(profession__icontains=query) |
            Q(place__icontains=query)
        ).order_by('name')

        serializer = ExecutiveSerializer(executives, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class ExecutiveAnalyticsView(APIView):
    permission_classes = [IsAdminUser]  
    authentication_classes =[JWTAuthentication]

    def get(self, request):
        try:
            from payments.models import ExecutivePayoutRedeem

            today = timezone.now()
            ten_days_ago = today - timedelta(days=10)

            total_executives = Executive.objects.count()
            online_executives = Executive.objects.filter(is_online=True).count()
            banned_executives = Executive.objects.filter(is_banned=True).count()
            active_executives = Executive.objects.filter(online=True).count()
            suspended_executives = Executive.objects.filter(is_suspended=True).count()
            recent_executives = Executive.objects.filter(created_at__gte=ten_days_ago).count()

            total_earned = ExecutiveStats.objects.aggregate(
                total=Coalesce(Sum('total_earnings'), Decimal('0.00'))
            )['total']

            total_withdrawn = ExecutivePayoutRedeem.objects.filter(status='paid').aggregate(
                total=Coalesce(
                    Sum(Coalesce('approved_amount', 'redemption_option__amount')),
                    Decimal('0.00')
                )
            )['total']

            data = {
                "total_executives": total_executives,
                "online_executives": online_executives,
                "active_executives":active_executives,
                "banned_executives": banned_executives,
                "suspended_executives": suspended_executives,
                "recently_joined_last_10_days": recent_executives,
                "total_earned_amount": total_earned,
                "total_withdrawn_amount": total_withdrawn,
            }

            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Pricing Management Views (Admin Only)

class GlobalPricingView(generics.RetrieveUpdateAPIView):
    """
    Admin view to manage global default pricing.
    GET: Retrieve current global pricing
    PUT/PATCH: Update global pricing
    """
    queryset = GlobalPricing.objects.all()
    serializer_class = GlobalPricingSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]
    
    def get_object(self):
        # Always return the first (and should be only) GlobalPricing instance
        obj, created = GlobalPricing.objects.get_or_create(
            defaults={'default_amount_per_min': Decimal('2.0')}
        )
        return obj


class RateScheduleListCreateView(generics.ListCreateAPIView):
    """
    Admin view to list and create rate schedules.
    """
    queryset = RateSchedule.objects.all()
    serializer_class = RateScheduleSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]
    ordering = ['-priority', 'name']


class RateScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Admin view to retrieve, update, or delete a specific rate schedule.
    """
    queryset = RateSchedule.objects.all()
    serializer_class = RateScheduleSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]
