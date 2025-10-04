from rest_framework import serializers
from .models import *
from decimal import Decimal

class RechargePlanCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RechargePlanCatogary
        fields = '__all__'
        read_only_fields = ['created_at', 'is_deleted']


class RechargePlanSerializer(serializers.ModelSerializer):
    final_price = serializers.SerializerMethodField()
    adjusted_coin_package = serializers.SerializerMethodField()
    total_talktime_minutes = serializers.SerializerMethodField()  
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = RechargePlan
        fields = '__all__'
        read_only_fields = ['is_deleted', 'total_talktime','category_name']  

    def get_final_price(self, obj):
        return obj.calculate_final_price()

    def get_adjusted_coin_package(self, obj):
        return obj.get_adjusted_coin_package()

    def get_total_talktime_minutes(self, obj):  
        minutes = obj.get_adjusted_coin_package() / 180
        return f"Your plan talktime is upto {minutes:.0f} minutes"

    def create(self, validated_data):
        instance = super().create(validated_data)
        instance.total_talktime = instance.calculate_talk_time_minutes()  
        instance.save()
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.total_talktime = instance.calculate_talk_time_minutes()  
        instance.save()
        return instance
    
    def get_category_name(self, obj):
        return obj.category_id.name if obj.category_id else None
    
class UserRechargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRecharge
        fields = ["id", "user", "plan", "coins_added", "amount_paid", "created_at", "is_successful"]
        read_only_fields = ["coins_added", "amount_paid", "created_at"]


class RedemptionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedemptionOption
        fields = ["id", "amount", "is_active", "is_deleted", "created_at"]
        read_only_fields = ["id", "created_at"]

class ExecutiveRedeemSerializer(serializers.ModelSerializer):
    redemption_option = serializers.PrimaryKeyRelatedField(
        queryset=RedemptionOption.objects.filter(is_deleted=False, is_active=True)
    )

    class Meta:
        model = ExecutivePayoutRedeem
        fields = [
            "redemption_option", "upi_details", "account_number", "ifsc_code"
        ]

from rest_framework import serializers
from .models import ExecutivePayoutRedeem

class ExecutiveRedeemHistorySerializer(serializers.ModelSerializer):
    redemption_amount = serializers.DecimalField(
        source="redemption_option.amount", 
        max_digits=12, 
        decimal_places=2, 
        read_only=True
    )

    class Meta:
        model = ExecutivePayoutRedeem
        fields = [
            "id",
            "redemption_amount",
            "status",
            "approved_amount",
            "notes",
            "upi_details",
            "account_number",
            "ifsc_code",
            "requested_at",
            "processed_at"
        ]