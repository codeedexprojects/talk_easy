from rest_framework import serializers
from executives.models import *
from django.contrib.auth.hashers import make_password


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

    class Meta:
        model = Executive
        fields = [
            'id', 'executive_id', 'mobile_number', 'name', 'age', 'email_id', 'gender',
            'profession', 'skills', 'place', 'education_qualification', 'status',
            'online', 'is_verified', 'is_suspended', 'is_banned', 'is_logged_out',
            'created_at', 'device_id', 'last_login', 'manager_executive',
            'account_number', 'ifsc_code', 'stats', 'is_offline', 'is_online',
            'on_call', 'password', 'languages_known'
        ]
        read_only_fields = ['id', 'created_at', 'last_login']

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
            "name",
            "is_online",
            "on_call",
            "is_banned",
            "is_suspended",
            "stats",
        ]