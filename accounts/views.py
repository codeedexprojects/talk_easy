
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

class SuperuserLoginView(generics.GenericAPIView):
    serializer_class = SuperuserLoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
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

        return Response({
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "user_id": admin.id,
            "email": admin.email,
            "role": admin.role,
            "is_superuser": admin.is_superuser,
            "is_staff": admin.is_staff,
        }, status=status.HTTP_200_OK)


#admin session logout ---------------------------------------------------------
class SessionSerializer(serializers.Serializer):
    session_key = serializers.CharField()
    expire_date = serializers.DateTimeField()
    ip_address = serializers.CharField(required=False)
    user_agent = serializers.CharField(required=False)


class LogoutAllSessionsAPIView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
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
    authentication_classes = [SessionAuthentication, TokenAuthentication]
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
    authentication_classes = [SessionAuthentication, TokenAuthentication]
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
    authentication_classes = [SessionAuthentication, TokenAuthentication]
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
