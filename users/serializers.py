from rest_framework import serializers
from users.models import *
from executives.models import Language
from executives.models import ExecutiveProfilePicture
from django.conf import settings

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user_id', 'name', 'email', 'mobile_number', 'gender', 
            'is_verified', 'is_banned', 'is_suspended', 'created_at','is_active'
        ]

class ReferralCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralCode
        fields = ['code', 'created_at']

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            "name",
            "email",
            "mobile_number",
            "gender",
        ]

class UserStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['is_suspended', 'is_banned']  

from executives.models import Executive
class ExecutiveFavoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Executive
        fields = [
            'id', 'executive_id', 'name', 'age', 'gender',
            'profession', 'skills', 'education_qualification', 'status',
            'online', 'is_verified', 'is_suspended', 'is_banned',
            'created_at','is_offline','is_online'
        ]
        read_only_fields = ['id', 'created_at']

class RatingSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.name', read_only=True)
    UID = serializers.CharField(source='user.user_id', read_only=True)
    id = serializers.IntegerField(source='executive.id', read_only=True)
    executive_name = serializers.CharField(source='executive.name', read_only=True)
    EXID = serializers.CharField(source='executive.executive_id', read_only=True)   



    class Meta:
        model = Rating
        fields = ['user_id', 'username','UID', 'id', 'executive_name','EXID', 'rating', 'comment', 'created_at']

class CareerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Career
        fields = '__all__'

class CarouselImageSerializer(serializers.ModelSerializer):

    class Meta:
        model = CarouselImage
        fields = ['id', 'title', 'image', 'created_at']

    # def get_full_image_url(self, obj):
    #     request = self.context.get('request')
    #     if obj.image:
    #         return request.build_absolute_uri(obj.image.url)
    #     return None

class ReferralHistorySerializer(serializers.ModelSerializer):
    referrer_id = serializers.IntegerField(source='referrer.id', read_only=True)
    referrer_name = serializers.CharField(source='referrer.name', read_only=True)
    referred_user_id = serializers.IntegerField(source='referred_user.id', read_only=True)
    referred_user_name = serializers.CharField(source='referred_user.name', read_only=True)

    class Meta:
        model = ReferralHistory
        fields = ['id', 'referrer_id', 'referrer_name', 'referred_user_id', 'referred_user_name', 'referred_at']


class UserStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStats
        fields = [
            'coin_balance',
            'total_calls',
            'total_call_seconds',
            'total_call_seconds_today',
            'last_updated'
        ]


class UserProfileSerializerAdmin(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id', 'user_id', 'name', 'email', 'mobile_number', 'gender',
             'is_verified', 'is_banned', 'is_suspended',
            'created_at', 'is_active', 'stats'
        ]

    def get_stats(self, obj):
        if hasattr(obj, 'stats'):
            return UserStatsSerializer(obj.stats).data
        return {
            "coin_balance": 0,
            "total_calls": 0,
            "total_call_seconds": 0,
            "total_call_seconds_today": 0,
            "last_updated": None
        }


class ExecutiveFavoriteSerializer(serializers.ModelSerializer):
    is_favourite = serializers.SerializerMethodField()

    class Meta:
        model = Executive
        fields = [
            'id', 'executive_id','name',
            'status','is_offline', 'is_online', 'on_call',
            'is_favourite',  
        ]

    def get_is_favourite(self, obj):
        request = self.context.get('request', None)
        if request and request.user.is_authenticated:
            return Favourite.objects.filter(user=request.user, executive=obj).exists()
        return False


class Executivelistserializer(serializers.ModelSerializer):
    languages_known = serializers.SlugRelatedField(many=True, slug_field='name', read_only=True)
    is_favourite = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Executive
        fields = [
            'id', 'executive_id', 'mobile_number', 'name', 'age', 'email_id', 'gender',
            'profession', 'skills', 'place', 'education_qualification', 'status',
            'online', 'is_verified', 'is_suspended', 'is_banned', 'is_logged_out',
            'created_at', 'device_id', 'last_login', 'manager_executive',
            'account_number', 'ifsc_code', 'stats', 'is_offline', 'is_online',
            'on_call', 'languages_known', 'is_favourite',
            'profile_photo_url'   
        ]
        read_only_fields = ['id', 'created_at', 'last_login', 'stats', 'is_favourite']

    def get_is_favourite(self, obj):
        user = self.context['request'].user
        return Favourite.objects.filter(user=user, executive=obj).exists()

    def get_profile_photo_url(self, obj):
        """Return the latest active profile photo of the executive"""
        request = self.context.get('request')
        profile_pic = ExecutiveProfilePicture.objects.filter(
            executive=obj, status="active"
        ).order_by("-created_at").first()

        if profile_pic and profile_pic.profile_photo:
            if request:
                return request.build_absolute_uri(profile_pic.profile_photo.url)
            return profile_pic.profile_photo.url
        return None

