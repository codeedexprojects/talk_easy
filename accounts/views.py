
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.serializers import *
from rest_framework import generics
from django.contrib.sessions.models import Session
from django.utils.decorators import method_decorator
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from .models import Admin  
from django.contrib.auth import logout
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.sessions.models import Session
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import AnonymousUser
from rest_framework import serializers
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils import timezone
from accounts.serializers import SuperuserLoginSerializer, AdminSessionSerializer
from .models import AdminSession
from .utils import parse_user_agent, get_client_ip
import uuid


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

        # Create refresh token with custom JTI
        refresh = RefreshToken.for_user(admin)
        
        # Generate unique JTI for tracking
        jti = str(uuid.uuid4())
        refresh['jti'] = jti
        refresh.access_token['jti'] = jti
        
        access_token = refresh.access_token
        
        # Store session information with device details
        session = self._store_login_session_info(request, admin, jti)
        
        # Get token info for response
        access_payload = access_token.payload
        refresh_payload = refresh.payload
        
        return Response({
            "access_token": str(access_token),
            "refresh_token": str(refresh),
            "user_id": admin.id,
            "email": admin.email,
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
                "issued_at": access_payload.get('iat')
            }
        }, status=status.HTTP_200_OK)
    
    def _store_login_session_info(self, request, admin, jti):
        """Store device and session information"""
        try:
            # Get client information
            ip_address = get_client_ip(request)
            user_agent_string = request.META.get('HTTP_USER_AGENT', '')
            
            # Parse device info
            device_info = parse_user_agent(user_agent_string)
            
            # Create session record
            session = AdminSession.objects.create(
                admin=admin,
                device_name=device_info['device_name'],
                device_type=device_info['device_type'],
                browser=device_info['browser'],
                os=device_info['os'],
                ip_address=ip_address,
                user_agent=user_agent_string,
                jwt_jti=jti,
                is_active=True
            )
            
            # Update admin's last login
            admin.last_login = timezone.now()
            admin.save(update_fields=['last_login'])
            
            return session
            
        except Exception as e:
            # Don't fail login if session info storage fails
            print(f"Error storing session info: {e}")
            # Return a dummy session object
            return type('obj', (object,), {
                'id': None,
                'device_type': 'unknown',
                'device_name': 'Unknown',
                'ip_address': ip_address
            })


from executives.models import Executive
from executives.serializers import ExecutiveSerializer
from .pagination import *
from rest_framework.permissions import IsAdminUser

class UnverifiedExecutivesListView(APIView):
    permission_classes = [IsAdminUser]  # replace with [IsAdminUser] later
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomExecutivePagination

    def get(self, request):
        executives = Executive.objects.filter(is_verified=False).order_by("-id")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(executives, request)
        serializer = ExecutiveSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class VerifyExecutiveView(APIView):
    permission_classes = [IsAdminUser]  # replace with [IsAdminUser] later
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
            "is_verified": executive.is_verified
        }, status=status.HTTP_200_OK)



class SuperuserSessionsListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Only superusers can view all superuser sessions
        if not request.user.is_superuser:
            return Response({
                'success': False,
                'message': 'Only superusers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get filter parameters
        user_id = request.query_params.get('user_id')
        active_only = request.query_params.get('active_only', 'true').lower() == 'true'
        
        # Build query
        sessions = AdminSession.objects.filter(admin__is_superuser=True).select_related('admin')
        
        if user_id:
            sessions = sessions.filter(admin_id=user_id)
        
        if active_only:
            sessions = sessions.filter(is_active=True)
        
        serializer = AdminSessionSerializer(sessions, many=True, context={'request': request})
        
        # Group sessions by admin
        sessions_by_admin = {}
        for session_data in serializer.data:
            email = session_data['admin_email']
            if email not in sessions_by_admin:
                sessions_by_admin[email] = {
                    'admin_email': email,
                    'admin_name': session_data['admin_name'],
                    'active_sessions': 0,
                    'sessions': []
                }
            
            sessions_by_admin[email]['sessions'].append(session_data)
            if session_data['is_active']:
                sessions_by_admin[email]['active_sessions'] += 1
        
        return Response({
            'success': True,
            'total_sessions': len(serializer.data),
            'total_admins': len(sessions_by_admin),
            'sessions_by_admin': list(sessions_by_admin.values())
        }, status=status.HTTP_200_OK)


class MyActiveSessionsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        sessions = AdminSession.objects.filter(
            admin=request.user,
            is_active=True
        )
        
        serializer = AdminSessionSerializer(sessions, many=True, context={'request': request})
        
        return Response({
            'success': True,
            'admin_email': request.user.email,
            'admin_name': request.user.name,
            'total_active_sessions': len(serializer.data),
            'sessions': serializer.data
        }, status=status.HTTP_200_OK)


class RevokeSessionView(APIView):
    """Revoke a specific session"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, session_id):
        try:
            session = AdminSession.objects.get(id=session_id)
        except AdminSession.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Users can only revoke their own sessions unless they're superuser
        if session.admin != request.user and not request.user.is_superuser:
            return Response({
                'success': False,
                'message': 'You can only revoke your own sessions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Don't allow revoking current session (use logout instead)
        if hasattr(request, 'jwt_jti') and session.jwt_jti == request.jwt_jti:
            return Response({
                'success': False,
                'message': 'Cannot revoke current session. Use logout instead.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        session.deactivate()
        
        return Response({
            'success': True,
            'message': 'Session revoked successfully',
            'session_id': session_id
        }, status=status.HTTP_200_OK)


class RevokeAllOtherSessionsView(APIView):
    """Revoke all sessions except current one"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        current_jti = getattr(request, 'jwt_jti', None)
        
        sessions = AdminSession.objects.filter(
            admin=request.user,
            is_active=True
        )
        
        if current_jti:
            sessions = sessions.exclude(jwt_jti=current_jti)
        
        count = sessions.count()
        sessions.update(is_active=False, logout_time=timezone.now())
        
        return Response({
            'success': True,
            'message': f'{count} session(s) revoked successfully',
            'sessions_revoked': count
        }, status=status.HTTP_200_OK)