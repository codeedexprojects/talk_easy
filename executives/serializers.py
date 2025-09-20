from rest_framework import serializers
from executives.models import *
from django.contrib.auth.hashers import make_password

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
    class Meta:
        model = ExecutiveStats
        fields = [
            'coins_per_second', 'set_coin', 'total_on_duty_seconds', 
            'total_talk_seconds_today', 'total_picked_calls', 'total_missed_calls', 'coin_balance'
        ]

class ExecutiveSerializer(serializers.ModelSerializer):
    stats = ExecutiveStatsSerializer(read_only=True) 

    class Meta:
        model = Executive
        fields = [
            'id', 'executive_id', 'mobile_number', 'name', 'age', 'email_id', 'gender',
            'profession', 'skills', 'place', 'education_qualification', 'status',
            'online', 'is_verified', 'is_suspended', 'is_banned', 'is_logged_out',
            'created_at', 'device_id', 'last_login', 'manager_executive',
            'account_number', 'ifsc_code', 'stats','is_offline','is_online','on_call'
        ]
        read_only_fields = ['id', 'created_at', 'last_login', 'stats']


class BlockUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedusersByExecutive
        fields = ['user', 'reason','is_blocked','executive']

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
            'profile_photo',
            'profile_photo_url',
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