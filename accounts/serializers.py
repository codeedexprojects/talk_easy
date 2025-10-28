from rest_framework import serializers
from django.utils import timezone
from .models import AdminSession
from .models import Admin
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken 
class SuperuserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class AdminSessionSerializer(serializers.ModelSerializer):
    admin_email = serializers.EmailField(source='admin.email', read_only=True)
    admin_name = serializers.CharField(source='admin.name', read_only=True)
    is_current = serializers.SerializerMethodField()
    session_duration = serializers.SerializerMethodField()
    
    class Meta:
        model = AdminSession
        fields = [
            'id', 'admin_email', 'admin_name', 'device_name', 'device_type',
            'browser', 'os', 'ip_address', 'is_active', 'last_activity',
            'login_time', 'logout_time', 'is_current', 'session_duration'
        ]
    
    def get_is_current(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'jwt_jti'):
            return False
        return obj.jwt_jti == request.jwt_jti
    
    def get_session_duration(self, obj):
        """Calculate how long the session has been active"""
        if obj.logout_time:
            duration = obj.logout_time - obj.login_time
        else:
            duration = timezone.now() - obj.login_time
        
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    
class SessionSerializer(serializers.Serializer):
    session_key = serializers.CharField()
    expire_date = serializers.DateTimeField()
    ip_address = serializers.CharField(required=False)
    user_agent = serializers.CharField(required=False)

class ManagerExecutiveCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = ['id', 'name', 'email', 'mobile_number', 'role', 'password']
        extra_kwargs = {
            'password': {'write_only': True},
            'role': {'read_only': True},
        }

    def create(self, validated_data):
        validated_data['role'] = 'manager_executive'
        password = validated_data.pop('password', None)

        admin = Admin.objects.create(**validated_data)
        if password:
            admin.set_password(password)
        admin.save()
        return admin

  
class ManagerExecutiveLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        user = authenticate(email=email, password=password)

        if user is None:
            raise serializers.ValidationError("Invalid credentials provided.")

        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")

        if user.role != 'manager_executive':
            raise serializers.ValidationError("You are not authorized as a Manager Executive.")

        refresh = RefreshToken.for_user(user)

        return {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
        }
    
class AdminPermissionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = ['id', 'name', 'email', 'role', 'custom_permissions']
        read_only_fields = ['email', 'name', 'role']