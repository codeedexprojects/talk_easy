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

class ManagerUserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = ['id', 'name', 'email', 'mobile_number', 'role', 'password']
        extra_kwargs = {
            'password': {'write_only': True},
            'role': {'read_only': True},
        }

    def create(self, validated_data):
        validated_data['role'] = 'manager_user'
        password = validated_data.pop('password', None)

        admin = Admin.objects.create(**validated_data)
        if password:
            admin.set_password(password)
        admin.save()
        return admin

class ManagerUserLoginSerializer(serializers.Serializer):
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

        if user.role != 'manager_user':
            raise serializers.ValidationError("You are not authorized as a Manager User.")

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


class AdminPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        email = attrs.get('email')
        otp = attrs.get('otp')
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')

        if new_password != confirm_password:
            raise serializers.ValidationError("Passwords do not match.")

        try:
            admin = Admin.objects.get(email=email)
        except Admin.DoesNotExist:
            raise serializers.ValidationError("Admin with this email does not exist.")

        # OTP verification
        if not admin.otp or admin.otp != otp:
            raise serializers.ValidationError("Invalid OTP.")

        # Optional: Expiry check (valid for 5 minutes)
        if admin.otp_created_at:
            time_diff = timezone.now() - admin.otp_created_at
            if time_diff.total_seconds() > 300:
                raise serializers.ValidationError("OTP has expired. Please request a new one.")

        attrs['admin'] = admin
        return attrs

    def save(self):
        admin = self.validated_data['admin']
        new_password = self.validated_data['new_password']

        admin.set_password(new_password)
        admin.otp = None
        admin.otp_verified_at = timezone.now()
        admin.save()

        return admin
    

class AdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = [
            'id',
            'name',
            'email',
            'mobile_number',
            'role',
            'custom_permissions',
            'is_banned',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'email', 'created_at']

    def validate_role(self, value):
        # Only superusers can change role
        request = self.context.get('request')
        if request and not request.user.role == 'superuser' and 'role' in self.initial_data:
            raise serializers.ValidationError("Only superusers can change role.")
        return value