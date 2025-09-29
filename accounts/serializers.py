from rest_framework import serializers
from django.utils import timezone
from .models import AdminSession

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