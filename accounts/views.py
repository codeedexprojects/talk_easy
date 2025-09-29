
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


#admin session logout ---------------------------------------------------------
class SessionSerializer(serializers.Serializer):
    """Serializer for session information"""
    session_key = serializers.CharField()
    expire_date = serializers.DateTimeField()
    ip_address = serializers.CharField(required=False)
    user_agent = serializers.CharField(required=False)


class LogoutAllSessionsAPIView(APIView):
    """
    API View to logout admin from all other sessions except current one
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        # Check if user is Admin instance
        if not isinstance(request.user, Admin):
            return Response({
                'success': False,
                'message': 'Unauthorized access. Admin account required.',
                'error_code': 'UNAUTHORIZED_USER_TYPE'
            }, status=status.HTTP_403_FORBIDDEN)
        
        current_session_key = request.session.session_key
        admin_user = request.user
        
        # Get all sessions for this user
        user_sessions = self._get_user_sessions(admin_user.id)
        
        # Delete all sessions except current one
        sessions_deleted = 0
        for session_data in user_sessions:
            if session_data['session_key'] != current_session_key:
                try:
                    Session.objects.get(session_key=session_data['session_key']).delete()
                    sessions_deleted += 1
                except Session.DoesNotExist:
                    continue
        
        return Response({
            'success': True,
            'message': f'Successfully logged out from {sessions_deleted} other sessions',
            'sessions_terminated': sessions_deleted,
            'current_session_preserved': True,
            'admin_info': {
                'name': admin_user.name,
                'email': admin_user.email,
                'role': admin_user.role
            }
        }, status=status.HTTP_200_OK)
    
    def get(self, request, *args, **kwargs):
        """Get active sessions count"""
        if not isinstance(request.user, Admin):
            return Response({
                'success': False,
                'message': 'Unauthorized access'
            }, status=status.HTTP_403_FORBIDDEN)
        
        user_sessions = self._get_user_sessions(request.user.id)
        current_session_key = request.session.session_key
        
        other_sessions = [s for s in user_sessions if s['session_key'] != current_session_key]
        
        return Response({
            'success': True,
            'total_sessions': len(user_sessions),
            'other_sessions': len(other_sessions),
            'current_session': current_session_key,
            'sessions': SessionSerializer(user_sessions, many=True).data
        }, status=status.HTTP_200_OK)
    
    def _get_user_sessions(self, user_id):
        """Helper method to get all sessions for a user"""
        user_sessions = []
        all_sessions = Session.objects.all()
        
        for session in all_sessions:
            try:
                session_data = session.get_decoded()
                if session_data.get('_auth_user_id') == str(user_id):
                    user_sessions.append({
                        'session_key': session.session_key,
                        'expire_date': session.expire_date,
                        'ip_address': session_data.get('ip_address', 'Unknown'),
                        'user_agent': session_data.get('user_agent', 'Unknown')
                    })
            except Exception:
                # Skip corrupted sessions
                continue
        
        return user_sessions


class LogoutAllAndCurrentAPIView(APIView):
    """
    API View to logout admin from ALL sessions including current one
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        if not isinstance(request.user, Admin):
            return Response({
                'success': False,
                'message': 'Unauthorized access. Admin account required.',
                'error_code': 'UNAUTHORIZED_USER_TYPE'
            }, status=status.HTTP_403_FORBIDDEN)
        
        admin_user = request.user
        
        # Get all sessions for this user
        user_sessions = self._get_user_sessions(admin_user.id)
        
        # Delete all sessions
        sessions_deleted = 0
        for session_data in user_sessions:
            try:
                Session.objects.get(session_key=session_data['session_key']).delete()
                sessions_deleted += 1
            except Session.DoesNotExist:
                continue
        
        # Delete auth tokens if using token authentication
        if hasattr(admin_user, 'auth_token'):
            admin_user.auth_token.delete()
        
        # Logout from current session
        logout(request)
        
        return Response({
            'success': True,
            'message': f'Successfully logged out from all {sessions_deleted} sessions',
            'sessions_terminated': sessions_deleted,
            'current_session_terminated': True,
            'redirect_required': True
        }, status=status.HTTP_200_OK)
    
    def _get_user_sessions(self, user_id):
        """Helper method to get all sessions for a user"""
        user_sessions = []
        all_sessions = Session.objects.all()
        
        for session in all_sessions:
            try:
                session_data = session.get_decoded()
                if session_data.get('_auth_user_id') == str(user_id):
                    user_sessions.append({
                        'session_key': session.session_key,
                        'expire_date': session.expire_date
                    })
            except Exception:
                continue
        
        return user_sessions


class ActiveSessionsAPIView(APIView):
    """
    API View to get all active sessions for current admin
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        if not isinstance(request.user, Admin):
            return Response({
                'success': False,
                'message': 'Unauthorized access'
            }, status=status.HTTP_403_FORBIDDEN)
        
        admin_user = request.user
        current_session_key = request.session.session_key
        
        # Get all sessions for this user with detailed info
        user_sessions = []
        all_sessions = Session.objects.all()
        
        for session in all_sessions:
            try:
                session_data = session.get_decoded()
                if session_data.get('_auth_user_id') == str(admin_user.id):
                    user_sessions.append({
                        'session_key': session.session_key,
                        'expire_date': session.expire_date,
                        'is_current': session.session_key == current_session_key,
                        'ip_address': session_data.get('ip_address', 'Unknown'),
                        'user_agent': session_data.get('user_agent', 'Unknown'),
                        'login_time': session_data.get('login_time', 'Unknown')
                    })
            except Exception:
                continue
        
        return Response({
            'success': True,
            'admin_info': {
                'id': admin_user.id,
                'name': admin_user.name,
                'email': admin_user.email,
                'role': admin_user.role,
                'role_display': admin_user.get_role_display()
            },
            'total_sessions': len(user_sessions),
            'current_session_key': current_session_key,
            'sessions': user_sessions
        }, status=status.HTTP_200_OK)


class TerminateSpecificSessionAPIView(APIView):
    """
    API View to terminate a specific session by session key
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, session_key, *args, **kwargs):
        if not isinstance(request.user, Admin):
            return Response({
                'success': False,
                'message': 'Unauthorized access'
            }, status=status.HTTP_403_FORBIDDEN)
        
        admin_user = request.user
        current_session_key = request.session.session_key
        
        # Prevent terminating current session through this endpoint
        if session_key == current_session_key:
            return Response({
                'success': False,
                'message': 'Cannot terminate current session. Use logout-all-and-current endpoint instead.',
                'error_code': 'CANNOT_TERMINATE_CURRENT_SESSION'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            session = Session.objects.get(session_key=session_key)
            session_data = session.get_decoded()
            
            # Verify the session belongs to the current admin
            if session_data.get('_auth_user_id') != str(admin_user.id):
                return Response({
                    'success': False,
                    'message': 'Session does not belong to current admin',
                    'error_code': 'SESSION_NOT_OWNED'
                }, status=status.HTTP_403_FORBIDDEN)
            
            session.delete()
            
            return Response({
                'success': True,
                'message': 'Session terminated successfully',
                'terminated_session': session_key
            }, status=status.HTTP_200_OK)
            
        except Session.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session not found or already terminated',
                'error_code': 'SESSION_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)

from executives.models import Executive
from executives.serializers import ExecutiveSerializer
from .pagination import *


class UnverifiedExecutivesListView(APIView):
    permission_classes = []  # replace with [IsAdminUser] later
    pagination_class = CustomExecutivePagination

    def get(self, request):
        executives = Executive.objects.filter(is_verified=False).order_by("-id")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(executives, request)
        serializer = ExecutiveSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class VerifyExecutiveView(APIView):
    permission_classes = []  # replace with [IsAdminUser] later

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
    """View all active sessions for superusers (Admin only)"""
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
    """View current user's active sessions"""
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