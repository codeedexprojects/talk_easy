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
            'account_number', 'ifsc_code', 'stats'
        ]
        read_only_fields = ['id', 'created_at', 'last_login', 'stats']
