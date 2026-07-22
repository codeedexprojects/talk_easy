import hashlib
from rest_framework import serializers
from executives.models import *
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


# ─────────────────────────────────────────────
# Executive forgot-password (OTP) helpers
# ─────────────────────────────────────────────

def _hash_otp(otp: str) -> str:
    """SHA-256 hash of a 6-digit OTP string."""
    return hashlib.sha256(otp.encode('utf-8')).hexdigest()


def _validate_strong_executive_password(value: str) -> str:
    """Enforce minimum password length only."""
    if len(value) < 8:
        raise serializers.ValidationError("Password must be at least 8 characters.")
    return value


class ExecutiveForgotPasswordRequestSerializer(serializers.Serializer):
    """Step 1: Executive submits mobile_number -> lookup -> send OTP (handled in the view)."""
    mobile_number = serializers.CharField(max_length=15)


class ExecutiveForgotPasswordVerifyOTPSerializer(serializers.Serializer):
    """Step 2: Executive submits mobile_number + OTP -> verifies hashed OTP."""
    mobile_number = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        mobile_number = attrs['mobile_number']
        otp_input = attrs['otp']

        otp_record = ExecutivePasswordResetOTP.objects.filter(
            mobile_number=mobile_number, is_verified=False
        ).first()
        if not otp_record:
            raise serializers.ValidationError({"otp": "No active OTP request found for this mobile number."})

        if otp_record.is_expired():
            otp_record.delete()
            raise serializers.ValidationError({"otp": "OTP has expired. Please request a new one."})

        if otp_record.attempts >= 3:
            otp_record.delete()
            raise serializers.ValidationError({"otp": "Too many failed attempts. Please request a new OTP."})

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
        # OTP stays valid for a short window after verification, to complete the reset
        otp_record.expires_at = timezone.now() + timedelta(minutes=10)
        otp_record.save(update_fields=['is_verified', 'expires_at'])
        return otp_record


class ExecutiveResetPasswordSerializer(serializers.Serializer):
    """Step 3: Reset password using a verified mobile_number OTP."""
    mobile_number = serializers.CharField(max_length=15)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return _validate_strong_executive_password(value)

    def validate(self, attrs):
        mobile_number = attrs['mobile_number']

        otp_record = ExecutivePasswordResetOTP.objects.filter(
            mobile_number=mobile_number, is_verified=True
        ).first()
        if not otp_record:
            raise serializers.ValidationError({"mobile_number": "OTP not verified for this mobile number."})

        if otp_record.is_expired():
            otp_record.delete()
            raise serializers.ValidationError({"mobile_number": "Verification window expired. Please verify again."})

        try:
            executive = Executive.objects.get(mobile_number=mobile_number)
        except Executive.DoesNotExist:
            raise serializers.ValidationError({"mobile_number": "No executive account found with this mobile number."})

        attrs['executive'] = executive
        attrs['otp_record'] = otp_record
        return attrs

    def save(self):
        executive = self.validated_data['executive']
        otp_record = self.validated_data['otp_record']

        executive.set_password(self.validated_data['new_password'])
        executive.save()

        # Password changed -> force re-login everywhere
        ExecutiveToken.objects.filter(executive=executive, revoked=False).update(
            revoked=True, revoked_at=timezone.now()
        )

        otp_record.delete()
        return executive


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id', 'name']

class ExecutiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Executive
        fields = '__all__'

    def create(self, validated_data):
        if 'password' in validated_data:
            validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


class ExecutiveLoginSerializer(serializers.Serializer):
    mobile_number = serializers.CharField()
    password = serializers.CharField(required=False, allow_blank=True)
    otp = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if not data.get("password") and not data.get("otp"):
            raise serializers.ValidationError("Either password or OTP is required.")
        return data



class ExecutiveLoginSerializer(serializers.Serializer):
    mobile_number = serializers.CharField()
    password = serializers.CharField()
    

class ExecutiveOTPVerifySerializer(serializers.Serializer):
    mobile_number = serializers.CharField()
    otp = serializers.CharField()



class ExecutiveStatsSerializer(serializers.ModelSerializer):
    executive_name = serializers.CharField(source="executive.name", read_only=True)

    class Meta:
        model = ExecutiveStats
        fields = ['executive_name','executive',
            'coins_per_second', 'amount_per_min', 'total_on_duty_seconds', 
            'total_talk_seconds_today', 'total_picked_calls', 'total_missed_calls', 'vault_Balance','total_earnings'
            ,'earnings_today','pending_payout','last_updated'
        ]

class ExecutiveSerializer(serializers.ModelSerializer):
    stats = ExecutiveStatsSerializer(required=False)
    password = serializers.CharField(write_only=True, required=False)    
    languages_known = serializers.SlugRelatedField(
        many=True,
        slug_field='name',
        queryset=Language.objects.all(),
        required=False
    )
    coins_per_second = serializers.SerializerMethodField()
    total_earned_amount = serializers.SerializerMethodField()
    total_withdrawn_amount = serializers.SerializerMethodField()

    class Meta:
        model = Executive
        fields = [
            'id', 'executive_id', 'username', 'mobile_number', 'name', 'age', 'email_id', 'gender',
            'profession', 'skills', 'place', 'education_qualification', 'status',
            'online', 'is_verified', 'is_suspended', 'is_banned', 'is_logged_out',
            'created_at', 'device_id', 'last_login', 'manager_executive',
            'account_number', 'ifsc_code', 'stats', 'is_offline', 'is_online',
            'on_call', 'password', 'languages_known', 'coins_per_second',
            'total_earned_amount', 'total_withdrawn_amount'
        ]
        read_only_fields = ['id', 'created_at', 'last_login']

    def get_coins_per_second(self, obj):
        """Get coins_per_second from ExecutiveStats"""
        if hasattr(obj, 'stats'):
            return obj.stats.coins_per_second
        return None

    def get_total_earned_amount(self, obj):
        if hasattr(obj, 'stats'):
            return obj.stats.total_earnings
        return Decimal('0.00')

    def get_total_withdrawn_amount(self, obj):
        from django.db.models import Sum
        from django.db.models.functions import Coalesce
        result = obj.payout_redeems.filter(status='paid').aggregate(
            total=Coalesce(
                Sum(Coalesce('approved_amount', 'redemption_option__amount')),
                Decimal('0.00')
            )
        )
        return result['total']

    def create(self, validated_data):
        languages = validated_data.pop("languages_known", [])
        password = validated_data.pop("password")
        stats_data = validated_data.pop("stats", None)

        executive = Executive(**validated_data)
        executive.set_password(password)
        executive.save()

        if languages:
            executive.languages_known.set(languages)

        if stats_data:
            ExecutiveStats.objects.create(executive=executive, **stats_data)

        return executive

    def update(self, instance, validated_data):
        languages = validated_data.pop("languages_known", None)
        password = validated_data.pop("password", None)
        stats_data = validated_data.pop("stats", {})

        stats_fields = {f.name for f in ExecutiveStats._meta.get_fields() if f.name != "id"}
        flat_stats = {k: validated_data.pop(k) for k in list(validated_data.keys()) if k in stats_fields}
        stats_data.update(flat_stats)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)
        instance.save()

        if languages is not None:
            instance.languages_known.set(languages)

        if stats_data:
            stats_instance = getattr(instance, "stats", None)
            if stats_instance:
                for attr, value in stats_data.items():
                    setattr(stats_instance, attr, value)
                stats_instance.save()
            else:
                ExecutiveStats.objects.create(executive=instance, **stats_data)

        return instance


class BlockedUserSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = BlockedusersByExecutive
        fields = ["id", "user_id", "user_name", "reason", "is_blocked", "blocked_at"]

class ExecutiveStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Executive
        fields = ['is_suspended', 'is_banned']

class ExecutiveOnlineStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Executive
        fields = ['is_online', 'is_offline']

class ExecutiveProfilePictureSerializer(serializers.ModelSerializer):   
    executive_name = serializers.CharField(source='executive.name', read_only=True)
    profile_photo_url = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = ExecutiveProfilePicture
        fields = [
            'id',
            'executive',
            'executive_name',
            'profile_photo_url',   # keep only absolute url
            'status',
            'status_display',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'executive']
    
    def get_profile_photo_url(self, obj):
        if obj.profile_photo:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.profile_photo.url)
            return obj.profile_photo.url
        return None
    
    def validate_profile_photo(self, value):
        if value:
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("Image file too large ( > 10MB )")            
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            if not any(value.name.lower().endswith(ext) for ext in valid_extensions):
                raise serializers.ValidationError(
                    "Invalid file format. Please upload JPG, JPEG, PNG, or GIF files only."
                )
        return value



class ExecutiveProfilePictureUploadSerializer(serializers.Serializer):
    profile_photo = serializers.ImageField(required=True)  
    def validate_profile_photo(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image file too large ( > 5MB )")
        
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
        if not any(value.name.lower().endswith(ext) for ext in valid_extensions):
            raise serializers.ValidationError(
                "Invalid file format. Please upload JPG, JPEG, PNG, or GIF files only."
            )
        
        return value
    
class AdminProfilePictureActionSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=500, 
        required=False, 
        allow_blank=True,
        help_text="Optional reason for rejection"
    )


class AdminProfilePictureListSerializer(serializers.ModelSerializer):
    executive_name = serializers.CharField(source='executive.name', read_only=True)
    executive_email = serializers.CharField(source='executive.email', read_only=True)
    executive_mobile = serializers.CharField(source='executive.mobile_number', read_only=True)
    profile_photo_url = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_since_upload = serializers.SerializerMethodField()
    
    class Meta:
        model = ExecutiveProfilePicture
        fields = [
            'id',
            'executive',
            'executive_name',
            'executive_email',
            'executive_mobile',
            'profile_photo',
            'profile_photo_url',
            'status',
            'status_display',
            'created_at',
            'updated_at',
            'days_since_upload'
        ]
    
    def get_profile_photo_url(self, obj):
        if obj.profile_photo:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.profile_photo.url)
            return obj.profile_photo.url
        return None
    
    def get_days_since_upload(self, obj):
        from django.utils import timezone
        delta = timezone.now() - obj.created_at
        return delta.days


class ExecutiveDetailSerializer(serializers.ModelSerializer):
    stats = ExecutiveStatsSerializer(read_only=True)

    class Meta:
        model = Executive
        fields = [
            "id",
            "username",
            "name",
            "is_online",
            "on_call",
            "is_banned",
            "is_suspended",
            "stats",
        ]

class BlockedUsersSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)
    executive_name = serializers.CharField(source='executive.name', read_only=True)
    executive_id = serializers.CharField(source='executive.executive_id',read_only=True)
    user_id = serializers.CharField(source='user.user_id', read_only=True)
    class Meta:
        model = BlockedusersByExecutive
        fields = [
            'id',
            'user',
            'user_name',
            'executive',
            'executive_name',
            'is_blocked',
            'reason',
            'blocked_at',
            'executive_id',
            'user_id'
        ]


# Pricing Serializers

class GlobalPricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalPricing
        fields = ['id', 'default_amount_per_min', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class RateScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateSchedule
        fields = [
            'id', 'name', 'amount_per_min', 'start_time', 'end_time',
            'days_of_week', 'active', 'priority', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
