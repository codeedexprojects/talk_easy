import hashlib
import re
from rest_framework import serializers
from django.utils import timezone
from django.conf import settings
from .models import AdminSession, Admin, AdminOTP
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken


# ─────────────────────────────────────────────
# Auth Serializers
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Admin Profile Serializer
# ─────────────────────────────────────────────

class AdminProfileSerializer(serializers.ModelSerializer):
    """
    Clean profile serializer — excludes OTP fields, passwords, and internal session data.
    Used for GET /admin-profile/ and PATCH /admin-profile/
    """
    class Meta:
        model = Admin
        fields = [
            'id', 'name', 'email', 'mobile_number', 'role',
            'profile_picture', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'role', 'created_at']

    def validate_mobile_number(self, value):
        if value and not re.match(r'^\+?[\d\s\-]{7,15}$', value):
            raise serializers.ValidationError("Enter a valid mobile number.")
        return value


# ─────────────────────────────────────────────
# Manager Serializers
# ─────────────────────────────────────────────

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
        user = authenticate(email=data['email'], password=data['password'])
        if user is None:
            raise serializers.ValidationError("Invalid credentials provided.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        if user.role != 'manager_executive':
            raise serializers.ValidationError("You are not authorized as a Manager Executive.")
        refresh = RefreshToken.for_user(user)
        return {
            'id': user.id, 'name': user.name, 'email': user.email,
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
        user = authenticate(email=data['email'], password=data['password'])
        if user is None:
            raise serializers.ValidationError("Invalid credentials provided.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        if user.role != 'manager_user':
            raise serializers.ValidationError("You are not authorized as a Manager User.")
        refresh = RefreshToken.for_user(user)
        return {
            'id': user.id, 'name': user.name, 'email': user.email,
            'role': user.role,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
        }


class AdminPermissionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = ['id', 'name', 'email', 'role', 'custom_permissions']
        read_only_fields = ['email', 'name', 'role']


# ─────────────────────────────────────────────
# Admin list/update (manager list view etc.)
# ─────────────────────────────────────────────

class AdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = [
            'id', 'name', 'email', 'mobile_number', 'role',
            'custom_permissions', 'is_banned', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'created_at']

    def validate_role(self, value):
        request = self.context.get('request')
        if request and not request.user.role == 'superuser' and 'role' in self.initial_data:
            raise serializers.ValidationError("Only superusers can change role.")
        return value


# ─────────────────────────────────────────────
# OTP Password Reset Serializers (Production-Grade)
# ─────────────────────────────────────────────

def _hash_otp(otp: str) -> str:
    """SHA-256 hash of a 6-digit OTP string."""
    return hashlib.sha256(otp.encode('utf-8')).hexdigest()


def _validate_strong_password(value: str) -> str:
    """Enforce strong password: min 8 chars, uppercase, digit, special char."""
    if len(value) < 8:
        raise serializers.ValidationError("Password must be at least 8 characters.")
    if not re.search(r'[A-Z]', value):
        raise serializers.ValidationError("Password must contain at least one uppercase letter.")
    if not re.search(r'\d', value):
        raise serializers.ValidationError("Password must contain at least one digit.")
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', value):
        raise serializers.ValidationError("Password must contain at least one special character.")
    return value


class AdminPhoneOTPRequestSerializer(serializers.Serializer):
    """Step 1: Admin submits phone → lookup admin → send OTP."""
    phone = serializers.CharField(max_length=15)

    def validate_phone(self, value):
        if not re.match(r'^\+?[\d\s\-]{7,15}$', value):
            raise serializers.ValidationError("Enter a valid phone number.")
        
        # We don't raise error if admin doesn't exist to prevent enumeration
        # But for phone-based, usually we check if it's a registered admin
        return value


class AdminPhoneOTPVerifySerializer(serializers.Serializer):
    """Step 2: Admin submits phone + OTP → verifies hashed OTP in AdminOTP table."""
    phone = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        phone = attrs['phone']
        otp_input = attrs['otp']

        # Find the latest OTP record for this phone
        otp_record = AdminOTP.objects.filter(phone=phone, is_verified=False).first()
        if not otp_record:
            raise serializers.ValidationError({"otp": "No active OTP request found for this phone number."})

        # Check expiry
        if otp_record.is_expired():
            otp_record.delete()
            raise serializers.ValidationError({"otp": "OTP has expired. Please request a new one."})

        # Enforce attempt limit (Max 3 as requested)
        if otp_record.attempts >= 3:
            otp_record.delete()
            raise serializers.ValidationError({"otp": "Too many failed attempts. Please request a new OTP."})

        # Compare hashed OTP
        if otp_record.otp_hash != _hash_otp(otp_input):
            otp_record.attempts += 1
            otp_record.save(update_fields=['attempts'])
            remaining = 3 - otp_record.attempts
            if remaining <= 0:
                otp_record.delete()
                raise serializers.ValidationError({"otp": "Too many failed attempts. Please request a new OTP."})
            raise serializers.ValidationError({"otp": f"Invalid OTP. {remaining} attempt(s) remaining."})

        attrs['otp_record'] = otp_record
        return attrs

    def save(self):
        otp_record = self.validated_data['otp_record']
        otp_record.is_verified = True
        # OTP is valid for a short window after verification
        otp_record.expires_at = timezone.now() + timezone.timedelta(minutes=10)
        otp_record.save(update_fields=['is_verified', 'expires_at'])
        return otp_record


class AdminPhoneResetPasswordSerializer(serializers.Serializer):
    """Step 3: Reset password using verified phone OTP."""
    phone = serializers.CharField(max_length=15)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return _validate_strong_password(value)

    def validate(self, attrs):
        phone = attrs['phone']

        # Find verified OTP record
        otp_record = AdminOTP.objects.filter(phone=phone, is_verified=True).first()
        if not otp_record:
            raise serializers.ValidationError({"phone": "OTP not verified for this phone number."})

        # Check if verified status hasn't expired (10 min window)
        if otp_record.is_expired():
            otp_record.delete()
            raise serializers.ValidationError({"phone": "Verification window expired. Please verify again."})

        # Find the admin with this phone
        try:
            admin = Admin.objects.get(mobile_number=phone, is_active=True)
        except Admin.DoesNotExist:
            raise serializers.ValidationError({"phone": "No admin account found with this phone number."})

        attrs['admin'] = admin
        attrs['otp_record'] = otp_record
        return attrs

    def save(self):
        admin = self.validated_data['admin']
        otp_record = self.validated_data['otp_record']
        
        admin.set_password(self.validated_data['new_password'])
        admin.save()
        
        # Cleanup
        otp_record.delete()
        return admin