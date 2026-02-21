
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import logout
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, serializers
import hashlib
import random
import uuid

from .models import Admin, AdminSession, AdminOTP
from .serializers import (
    SuperuserLoginSerializer,
    AdminSessionSerializer,
    AdminProfileSerializer,
    AdminUpdateSerializer,
    AdminPermissionUpdateSerializer,
    ManagerExecutiveCreateSerializer,
    ManagerExecutiveLoginSerializer,
    ManagerUserCreateSerializer,
    ManagerUserLoginSerializer,
    AdminPhoneOTPRequestSerializer,
    AdminPhoneOTPVerifySerializer,
    AdminPhoneResetPasswordSerializer,
)
from .utils import parse_user_agent, get_client_ip
from .pagination import CustomExecutivePagination
from executives.permissions import IsAdminUser
from executives.models import Executive
from executives.serializers import ExecutiveSerializer
from executives.utils import send_otp



# ─────────────────────────────────────────────
# Superuser Login
# ─────────────────────────────────────────────

class SuperuserLoginView(APIView):
    serializer_class = SuperuserLoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        admin = authenticate(request, email=email, password=password)

        if not admin:
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        if not admin.is_superuser:
            return Response({"detail": "Only superusers can log in here."}, status=status.HTTP_403_FORBIDDEN)

        if getattr(admin, "role", None) != "superuser":
            admin.role = "superuser"
            admin.save(update_fields=["role"])

        refresh = RefreshToken.for_user(admin)
        jti = str(uuid.uuid4())
        refresh['jti'] = jti
        refresh.access_token['jti'] = jti
        access_token = refresh.access_token

        session = self._store_login_session_info(request, admin, jti)

        access_payload = access_token.payload
        refresh_payload = refresh.payload

        return Response({
            "access_token": str(access_token),
            "refresh_token": str(refresh),
            "user_id": admin.id,
            "email": admin.email,
            "mobile": admin.mobile_number,
            "role": admin.role,
            "is_superuser": admin.is_superuser,
            "is_staff": admin.is_staff,
            "session_info": {
                "session_id": session.id,
                "device_type": session.device_type,
                "device_name": session.device_name,
                "ip_address": session.ip_address,
            },
            "token_info": {
                "access_expires_at": access_payload.get('exp'),
                "refresh_expires_at": refresh_payload.get('exp'),
                "issued_at": access_payload.get('iat'),
            }
        }, status=status.HTTP_200_OK)

    def _store_login_session_info(self, request, admin, jti):
        ip_address = get_client_ip(request)
        try:
            user_agent_string = request.META.get('HTTP_USER_AGENT', '')
            device_info = parse_user_agent(user_agent_string)
            session = AdminSession.objects.create(
                admin=admin,
                device_name=device_info['device_name'],
                device_type=device_info['device_type'],
                browser=device_info['browser'],
                os=device_info['os'],
                ip_address=ip_address,
                user_agent=user_agent_string,
                jwt_jti=jti,
                is_active=True,
            )
            admin.last_login = timezone.now()
            admin.save(update_fields=['last_login'])
            return session
        except Exception as e:
            print(f"Error storing session info: {e}")
            return type('obj', (object,), {
                'id': None, 'device_type': 'unknown',
                'device_name': 'Unknown', 'ip_address': ip_address
            })


# ─────────────────────────────────────────────
# Admin Profile (JWT Protected)
# ─────────────────────────────────────────────

class AdminProfileView(APIView):
    """
    GET  /accounts/admin-profile/          → View own profile
    PATCH /accounts/admin-profile/         → Update own profile
    Superuser can also GET/PATCH /<pk>/ via AdminUpdateView for managing other admins.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        serializer = AdminProfileSerializer(request.user, context={'request': request})
        return Response({
            "success": True,
            "data": serializer.data,
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = AdminProfileSerializer(
            request.user, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Profile updated successfully.",
                "data": serializer.data,
            }, status=status.HTTP_200_OK)
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────
# Admin Update (Superuser manages other admins)
# ─────────────────────────────────────────────

class AdminUpdateView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request, pk=None):
        try:
            admin = Admin.objects.get(pk=pk) if (request.user.role == 'superuser' and pk) else request.user
        except Admin.DoesNotExist:
            return Response({"error": "Admin not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminUpdateSerializer(admin, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk=None):
        try:
            admin = Admin.objects.get(pk=pk) if (request.user.role == 'superuser' and pk) else request.user
        except Admin.DoesNotExist:
            return Response({"error": "Admin not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminUpdateSerializer(admin, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Admin profile updated successfully.", "data": serializer.data},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────
# Phone OTP Password Reset — 3-Step Flow
# ─────────────────────────────────────────────

class AdminSendOTPView(APIView):
    """
    POST /accounts/admin/password-reset/send-otp/
    Step 1: Admin submits phone → lookup admin → send OTP via SMS.
    Rate limited to 1 request per 60 seconds per phone number.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminPhoneOTPRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        phone = serializer.validated_data['phone']

        # Check if Admin exists with this phone
        admin_exists = Admin.objects.filter(mobile_number=phone, is_active=True).exists()
        if not admin_exists:
            # Still return true to prevent user enumeration
            return Response({"status": True, "message": "OTP sent successfully"}, status=status.HTTP_200_OK)

        # Rate-limiting: Check latest OTP for this phone
        latest_otp = AdminOTP.objects.filter(phone=phone).first()
        if latest_otp:
            time_diff = (timezone.now() - latest_otp.created_at).total_seconds()
            if time_diff < 60:
                return Response({
                    "status": False,
                    "message": f"Please wait {int(60 - time_diff)} seconds before requesting a new OTP."
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Generate OTP
        otp_code = str(random.randint(100000, 999999))
        otp_hash = hashlib.sha256(otp_code.encode('utf-8')).hexdigest()

        # Send via service
        sms_sent = send_otp(phone, otp_code)
        if not sms_sent:
            return Response({"status": False, "message": "Failed to send OTP via SMS. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store hashed OTP (one active per phone)
        AdminOTP.objects.filter(phone=phone).delete()  # Clean up old ones
        AdminOTP.objects.create(
            phone=phone,
            otp_hash=otp_hash,
            expires_at=timezone.now() + timezone.timedelta(minutes=5)
        )

        return Response({"status": True, "message": "OTP sent successfully"}, status=status.HTTP_200_OK)


class AdminVerifyOTPView(APIView):
    """
    POST /accounts/admin/password-reset/verify-otp/
    Step 2: Admin submits phone + OTP → verify hash, enforce 3 attempts.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminPhoneOTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"status": True, "message": "OTP verified"}, status=status.HTTP_200_OK)
        return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class AdminPasswordResetView(APIView):
    """
    POST /accounts/admin/password-reset/reset/
    Step 3: Reset password using verified phone OTP.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminPhoneResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"status": True, "message": "Password reset successful"}, status=status.HTTP_200_OK)
        return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)



# ─────────────────────────────────────────────
# Executive Verification
# ─────────────────────────────────────────────

class UnverifiedExecutivesListView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomExecutivePagination

    def get(self, request):
        executives = Executive.objects.filter(is_verified=False).order_by("-id")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(executives, request)
        serializer = ExecutiveSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class VerifyExecutiveView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, id):
        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"message": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)

        is_verified = request.data.get("is_verified")
        if is_verified is None:
            return Response({"message": "is_verified field is required"}, status=status.HTTP_400_BAD_REQUEST)

        executive.is_verified = bool(is_verified)
        executive.save(update_fields=["is_verified"])
        return Response({
            "message": "Executive verification status updated",
            "executive_id": executive.id,
            "is_verified": executive.is_verified,
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────
# Session Management
# ─────────────────────────────────────────────

class SuperuserSessionsListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_superuser:
            return Response({'success': False, 'message': 'Only superusers can access this endpoint'}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.query_params.get('user_id')
        active_only = request.query_params.get('active_only', 'true').lower() == 'true'
        sessions = AdminSession.objects.filter(admin__is_superuser=True).select_related('admin')

        if user_id:
            sessions = sessions.filter(admin_id=user_id)
        if active_only:
            sessions = sessions.filter(is_active=True)

        serializer = AdminSessionSerializer(sessions, many=True, context={'request': request})
        sessions_by_admin = {}
        for session_data in serializer.data:
            email = session_data['admin_email']
            if email not in sessions_by_admin:
                sessions_by_admin[email] = {
                    'admin_email': email,
                    'admin_name': session_data['admin_name'],
                    'active_sessions': 0,
                    'sessions': [],
                }
            sessions_by_admin[email]['sessions'].append(session_data)
            if session_data['is_active']:
                sessions_by_admin[email]['active_sessions'] += 1

        return Response({
            'success': True,
            'total_sessions': len(serializer.data),
            'total_admins': len(sessions_by_admin),
            'sessions_by_admin': list(sessions_by_admin.values()),
        }, status=status.HTTP_200_OK)


class MyActiveSessionsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = AdminSession.objects.filter(admin=request.user, is_active=True)
        serializer = AdminSessionSerializer(sessions, many=True, context={'request': request})
        return Response({
            'success': True,
            'admin_email': request.user.email,
            'admin_name': request.user.name,
            'total_active_sessions': len(serializer.data),
            'sessions': serializer.data,
        }, status=status.HTTP_200_OK)


class RevokeSessionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = AdminSession.objects.get(id=session_id)
        except AdminSession.DoesNotExist:
            return Response({'success': False, 'message': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)

        if session.admin != request.user and not request.user.is_superuser:
            return Response({'success': False, 'message': 'You can only revoke your own sessions'}, status=status.HTTP_403_FORBIDDEN)

        if hasattr(request, 'jwt_jti') and session.jwt_jti == request.jwt_jti:
            return Response({'success': False, 'message': 'Cannot revoke current session. Use logout instead.'}, status=status.HTTP_400_BAD_REQUEST)

        session.deactivate()
        return Response({'success': True, 'message': 'Session revoked successfully', 'session_id': session_id}, status=status.HTTP_200_OK)


class RevokeAllOtherSessionsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_jti = getattr(request, 'jwt_jti', None)
        sessions = AdminSession.objects.filter(admin=request.user, is_active=True)
        if current_jti:
            sessions = sessions.exclude(jwt_jti=current_jti)
        count = sessions.count()
        sessions.update(is_active=False, logout_time=timezone.now())
        return Response({'success': True, 'message': f'{count} session(s) revoked successfully', 'sessions_revoked': count}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────
# Manager Management
# ─────────────────────────────────────────────

class ManagerExecutiveCreateView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "You do not have permission to create this role."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ManagerExecutiveCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Manager Executive created successfully", "data": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManagerExecutiveLoginView(APIView):
    def post(self, request):
        serializer = ManagerExecutiveLoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response({"message": "Login successful", "data": serializer.validated_data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManagerExecutiveDeleteView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, pk):
        if not (request.user.is_superuser or getattr(request.user, "role", "") == "admin"):
            return Response({"error": "You do not have permission to delete a manager executive."}, status=status.HTTP_403_FORBIDDEN)
        manager_exec = get_object_or_404(Admin, id=pk, role="manager_executive")
        manager_exec.delete()
        return Response({"message": "Manager executive deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class ManagerUserCreateView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        if not request.user.is_superuser:
            return Response({"error": "You do not have permission to create this role."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ManagerUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Manager User created successfully", "data": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManagerUserLoginView(APIView):
    def post(self, request):
        serializer = ManagerUserLoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response({"message": "Login successful", "data": serializer.validated_data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManagerUserDeleteView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, pk):
        if not (request.user.is_superuser or getattr(request.user, "role", "") == "admin"):
            return Response({"error": "You do not have permission to delete a manager user."}, status=status.HTTP_403_FORBIDDEN)
        manager_user = get_object_or_404(Admin, id=pk, role="manager_user")
        manager_user.delete()
        return Response({"message": "Manager user deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class UpdateAdminPermissionsView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, pk):
        if not request.user.is_superuser:
            return Response({"error": "Only superusers can manage permissions."}, status=status.HTTP_403_FORBIDDEN)
        try:
            admin = Admin.objects.get(pk=pk)
        except Admin.DoesNotExist:
            return Response({"error": "Admin not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminPermissionUpdateSerializer(admin, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Permissions updated successfully", "data": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManagerListView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        role_type = request.query_params.get("role")
        managers = Admin.objects.filter(role__startswith="manager")
        if role_type:
            managers = managers.filter(role=role_type)
        serializer = AdminUpdateSerializer(managers, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ManagerDetailView(APIView):
    """
    GET /accounts/managers/<id>/
    Retrieve details of a specific manager by ID.
    Accessible only by admins/superusers.
    """
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request, pk):
        manager = get_object_or_404(Admin, pk=pk, role__startswith="manager")
        serializer = AdminUpdateSerializer(manager, context={'request': request})
        return Response({
            "status": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)