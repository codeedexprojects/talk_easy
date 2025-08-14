import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from users.authentication import UserProfileJWTAuthentication
from users.models import  ReferralCode, ReferralHistory, DeletedUser,UserProfile
from executives.utils import send_otp
from rest_framework.permissions import IsAuthenticated
from users.serializers import *
from rest_framework_simplejwt.tokens import RefreshToken


class UserProfileRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token['user_id'] = str(user.id)
        return token

    @classmethod
    def from_token(cls, token):
        return cls(token)


class RegisterOrLoginView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        mobile_number = request.data.get('mobile_number')
        referral_code = request.data.get('referral_code')
        otp = str(random.randint(100000, 999999))

        if not mobile_number:
            return Response({"message": "Mobile number is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the user exists
        try:
            user = UserProfile.objects.get(mobile_number=mobile_number)

            # If user is banned
            if user.is_banned:
                return Response({
                    'message': 'User is banned and cannot log in.',
                    'is_banned': True,
                    'is_existing_user': True
                }, status=status.HTTP_403_FORBIDDEN)

            # Send OTP
            try:
                send_otp(mobile_number, otp)
            except Exception as e:
                return Response({
                    'message': 'Failed to send OTP. Please try again later.',
                    'error': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Save OTP
            user.otp = otp
            user.save(update_fields=['otp'])

            # Referral for existing users only if they have never been referred
            if referral_code and not ReferralHistory.objects.filter(referred_user=user).exists():
                try:
                    referrer = ReferralCode.objects.get(code=referral_code).user
                    ReferralHistory.objects.create(referrer=referrer, referred_user=user)
                    referrer.coin_balance += 1000
                    referrer.save(update_fields=['coin_balance'])
                except ReferralCode.DoesNotExist:
                    return Response({'message': 'Invalid referral code.', 'status': False},
                                    status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'message': 'Login OTP sent to your mobile number.',
                'user_id': user.id,
                'mobile_number': user.mobile_number,
                'otp': user.otp,
                'status': True,
                'is_existing_user': True,
                'user_main_id': user.user_id,
            }, status=status.HTTP_200_OK)

        except UserProfile.DoesNotExist:
            is_deleted_user = DeletedUser.objects.filter(mobile_number=mobile_number).exists()
            initial_coin_balance = 0 if is_deleted_user else 1000

            # Send OTP
            try:
                send_otp(mobile_number, otp)
            except Exception as e:
                return Response({
                    'message': 'Failed to send OTP. Please try again later.',
                    'error': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Create new user
            user = UserProfile.objects.create(
                mobile_number=mobile_number,
                otp=otp,
                coin_balance=initial_coin_balance
            )

            # Create referral only for new users who are not deleted
            if referral_code and not is_deleted_user:
                try:
                    referrer = ReferralCode.objects.get(code=referral_code).user
                    ReferralHistory.objects.create(referrer=referrer, referred_user=user)
                    referrer.coin_balance += 1000
                    referrer.save(update_fields=['coin_balance'])
                except ReferralCode.DoesNotExist:
                    return Response({'message': 'Invalid referral code.', 'status': False},
                                    status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'message': 'Registration OTP sent to your mobile number.',
                'status': True,
                'is_existing_user': False,
                'user_id': user.id,
                'mobile_number': user.mobile_number,
                'otp': user.otp,
                'coin_balance': user.coin_balance,
                'user_main_id': user.user_id,
            }, status=status.HTTP_200_OK)


from rest_framework_simplejwt.tokens import RefreshToken , TokenError


from users.utils import create_tokens_for_userprofile

class VerifyOTPView(APIView):
    permission_classes = []
    
    def post(self, request):
        mobile_number = request.data.get('mobile_number')
        otp = request.data.get('otp')
        name = request.data.get('name')
        gender = request.data.get('gender')
        
        if not mobile_number or not otp:
            return Response({
                'message': 'Mobile number and OTP are required.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = UserProfile.objects.get(mobile_number=mobile_number, otp=otp)
            is_existing_user = user.is_verified
            
            user.otp = None
            user.is_verified = True
            
            if not is_existing_user and name and gender:
                user.name = name
                user.gender = gender
            
            user.save()
            
            tokens = create_tokens_for_userprofile(user)
            
            return Response({
                'message': 'OTP verified successfully.',
                'user_id': user.id,
                'user_main_id': user.user_id,
                'is_existing_user': is_existing_user,
                'access_token': tokens['access'],
                'refresh_token': tokens['refresh'],
            }, status=status.HTTP_200_OK)
            
        except UserProfile.DoesNotExist:
            return Response({
                'message': 'Invalid mobile number or OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'message': f'An error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [UserProfileJWTAuthentication]
    
    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return Response({'message': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            token = RefreshToken(refresh_token)
            
            if hasattr(request, 'user') and request.user:
                user = request.user
            else:
                user_id = token.payload.get('user_id')
                if not user_id:
                    return Response({'message': 'Invalid token payload.'}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    user = UserProfile.objects.get(id=user_id)
                except UserProfile.DoesNotExist:
                    return Response({'message': 'User not found.'}, status=status.HTTP_400_BAD_REQUEST)
            
            user.is_active = False
            user.is_loginned = False
            user.is_online = False
            user.save(update_fields=['is_active', 'is_loginned', 'is_online'])
            
            token.blacklist()
            
            return Response({'message': 'Logout successful.'}, status=status.HTTP_200_OK)
            
        except TokenError:
            return Response({'message': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'message': f'An error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [UserProfileJWTAuthentication]

    def get_user_instance(self, request, user_id):
        if user_id:
            return UserProfile.objects.filter(id=user_id).first()
        return request.user

    def get(self, request, user_id=None):
        user = self.get_user_instance(request, user_id)
        if not user:
            return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserProfileSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, user_id=None):
        user = self.get_user_instance(request, user_id)
        if not user:
            return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "User updated successfully", "data": serializer.data},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
class UserReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            referral_code = user.referral_code  
        except ReferralCode.DoesNotExist:
            return Response({'message': 'Referral code not found for this user.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReferralCodeSerializer(referral_code)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class UserCoinBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        coin_balance = getattr(user, 'coin_balance', None)
        if coin_balance is None:
            return Response({"message": "Coin balance not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "user_id": user.id,
            "coin_balance": coin_balance
        }, status=status.HTTP_200_OK)


from executives.models import *
from executives.serializers import *
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

class ExecutiveListAPIView(APIView):
    permission_classes = [IsAuthenticated]  

    def get(self, request):
        executives = Executive.objects.all().order_by('-created_at')
        serializer = ExecutiveSerializer(executives, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ExecutiveSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            # Notify WebSocket group
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "executives_group",
                {
                    "type": "send_executives_list"
                }
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from rest_framework_simplejwt.authentication import JWTAuthentication

class UpdateUserStatusAPIView(APIView):
    permission_classes = [IsAuthenticated] 
    authentication_classes = [JWTAuthentication]

    def patch(self, request, user_id):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized.", "status": False}, status=status.HTTP_403_FORBIDDEN)

        try:
            target_user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"detail": "User not found.", "status": False}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserStatusUpdateSerializer(target_user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "User status updated successfully.", "status": True}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)