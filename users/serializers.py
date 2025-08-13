from rest_framework import serializers
from users.models import *

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user_id', 'name', 'email', 'mobile_number', 'gender', 'coin_balance', 
            'is_verified', 'is_banned', 'is_suspended', 'created_at','is_active'
        ]

class ReferralCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralCode
        fields = ['code', 'created_at']