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
            if user.is_banned and not user.is_deleted:
                return Response({
                    'message': 'User is banned or deleted cannot log in.',
                    'is_banned': True,
                    'is_existing_user': True,
                    'is_deleted': user.is_deleted
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
                    
                    # ✅ Update referrer coins in UserStats
                    referrer_stats = getattr(referrer, "stats", None)
                    if referrer_stats:
                        referrer_stats.coin_balance += 1000
                        referrer_stats.save(update_fields=['coin_balance'])
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
            )

            user_stats, created = UserStats.objects.get_or_create(user=user)
            if initial_coin_balance > 0:
                user_stats.coin_balance = initial_coin_balance
                user_stats.save(update_fields=['coin_balance'])

            if referral_code and not is_deleted_user:
                try:
                    referrer = ReferralCode.objects.get(code=referral_code).user
                    ReferralHistory.objects.create(referrer=referrer, referred_user=user)
                    
                    referrer_stats = getattr(referrer, "stats", None)
                    if referrer_stats:
                        referrer_stats.coin_balance += 1000
                        referrer_stats.save(update_fields=['coin_balance'])
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
                'coin_balance': user_stats.coin_balance, 
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

        if not hasattr(user, "stats"):
            return Response(
                {"message": "User stats not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "user_id": user.id,
            "coin_balance": user.stats.coin_balance
        }, status=status.HTTP_200_OK)



from executives.models import *
from executives.serializers import *
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from accounts.pagination import CustomUserPagination

class ExecutiveListAPIView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomUserPagination

    def get(self, request):
        executives = Executive.objects.all().order_by('-created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(executives, request, view=self)

        serializer = Executivelistserializer(page, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = Executivelistserializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
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
    
from django.shortcuts import get_object_or_404

class RatingExecutiveView(APIView):
    permission_classes = []

    def get(self, request, executive_id, *args, **kwargs):
        executive = get_object_or_404(Executive, id=executive_id)
        ratings = Rating.objects.filter(executive=executive)
        serializer = RatingSerializer(ratings, many=True)
        average_rating = ratings.aggregate(avg_rating=models.Avg('rating'))['avg_rating'] or 0
        return Response({
            "executive_id": executive.id,
            "executive_name": executive.name,
            "average_rating": round(average_rating, 2),
            "ratings": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, executive_id, *args, **kwargs):
        user_id = request.data.get('user_id')
        rating_value = request.data.get('rating')
        comment = request.data.get('comment', '')

        if not user_id or rating_value is None:
            return Response({"message": "user_id and rating are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(UserProfile, id=user_id)
        executive = get_object_or_404(Executive, id=executive_id)

        rating, created = Rating.objects.update_or_create(
            user=user,
            executive=executive,
            defaults={"rating": rating_value, "comment": comment}
        )

        serializer = RatingSerializer(rating)
        message = "Rating added successfully." if created else "Rating updated successfully."
        return Response({"message": message, "rating": serializer.data},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request, executive_id, *args, **kwargs):
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({"message": "user_id is required to delete a rating."},
                            status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(UserProfile, id=user_id)
        executive = get_object_or_404(Executive, id=executive_id)

        rating = Rating.objects.filter(user=user, executive=executive).first()
        if not rating:
            return Response({"message": "Rating not found."}, status=status.HTTP_404_NOT_FOUND)

        rating.delete()
        return Response({"message": "Rating removed successfully."}, status=status.HTTP_200_OK)
    

class CareerListCreateView(APIView):

    def get(self, request, *args, **kwargs):
        careers = Career.objects.all().order_by('-created_at')
        serializer = CareerSerializer(careers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = CareerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CareerDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Career, pk=pk)

    def get(self, request, pk, *args, **kwargs):
        career = self.get_object(pk)
        serializer = CareerSerializer(career)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk, *args, **kwargs):
        career = self.get_object(pk)
        serializer = CareerSerializer(career, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk, *args, **kwargs):
        career = self.get_object(pk)
        serializer = CareerSerializer(career, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, *args, **kwargs):
        career = self.get_object(pk)
        career.delete()
        return Response({"message": "Career entry deleted successfully."}, status=status.HTTP_200_OK)
    
class CarouselImageListCreateView(APIView):
    def get(self, request):
        images = CarouselImage.objects.all()
        serializer = CarouselImageSerializer(images, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CarouselImageSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CarouselImageDetailView(APIView):
    def get(self, request, image_id):
        try:
            image = CarouselImage.objects.get(id=image_id)
            serializer = CarouselImageSerializer(image)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CarouselImage.DoesNotExist:
            return Response({'message': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, image_id):
        try:
            image = CarouselImage.objects.get(id=image_id)
            serializer = CarouselImageSerializer(image, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except CarouselImage.DoesNotExist:
            return Response({'message': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, image_id):
        try:
            image = CarouselImage.objects.get(id=image_id)
            image.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CarouselImage.DoesNotExist:
            return Response({'message': 'Image not found'}, status=status.HTTP_404_NOT_FOUND)

from rest_framework.permissions import IsAdminUser    
class ReferralHistoryListView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request, *args, **kwargs):
        histories = ReferralHistory.objects.select_related('referrer', 'referred_user').all().order_by('-referred_at')
        serializer = ReferralHistorySerializer(histories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

from rest_framework.generics import ListAPIView,RetrieveAPIView
from accounts.pagination import CustomUserPagination
from rest_framework import generics

class UserProfileListView(ListAPIView):
    queryset = UserProfile.objects.filter(is_deleted=False).order_by('-created_at')
    serializer_class = UserProfileSerializerAdmin
    pagination_class = CustomUserPagination

class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializerAdmin
    permission_classes = [IsAuthenticated] 

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return get_object_or_404(UserProfile, id=user_id)
    
class UserDetailViewAdmin(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializerAdmin
    permission_classes = [IsAdminUser]
    authentication_classes =[JWTAuthentication] 

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return get_object_or_404(UserProfile, id=user_id)
    
from rest_framework.permissions import IsAdminUser
from django.db.models import Q

class UserSoftDeleteView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]
    
    def delete(self, request, user_id=None):
        try:
            if user_id:
                if not request.user.is_staff:
                    return Response(
                        {"error": "Permission denied. Admin access required."}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
                user = get_object_or_404(UserProfile, id=user_id)
            else:
                user = request.user
            
            if user.is_deleted:
                return Response(
                    {"error": "User account is already deleted"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )            
            user.is_deleted = True
            user.is_active = False  
            user.is_online = False  
            user.is_loginned = False  
            user.save()
            
            deletion_log = {
                "user_id": user.user_id,
                "deleted_at": timezone.now().isoformat(),
                "deleted_by": request.user.user_id if hasattr(request.user, 'user_id') else str(request.user.id)
            }
            
            return Response({
                "message": "User account has been successfully deleted",
                "user_id": user.user_id,
                "deleted_at": timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DeleteUserAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        try:
            user = UserProfile.objects.get(id=user_id, is_deleted=False)
        except UserProfile.DoesNotExist:
            return Response({"error": "User not found or already deleted"}, status=status.HTTP_404_NOT_FOUND)

        if request.user.id != user.id:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        user.is_deleted = True
        user.is_active = False
        user.save()

        return Response({"message": "User account deleted successfully"}, status=status.HTTP_200_OK)


class UserAccountRestoreView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]
    
    def post(self, request, user_id):
        try:
            user = get_object_or_404(UserProfile, id=user_id)
            
            if not user.is_deleted:
                return Response(
                    {"error": "User account is not deleted"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user.is_deleted = False
            user.is_active = True 
            user.save()
            
            serializer = UserProfileSerializer(user)
            
            return Response({
                "message": "User account has been successfully restored",
                "user": serializer.data
            }, status=status.HTTP_200_OK)
            
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class UserBulkSoftDeleteView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]
    
    def delete(self, request):
        user_ids = request.data.get('user_ids', [])
        reason = request.data.get('reason', '')
        
        if not user_ids or not isinstance(user_ids, list):
            return Response(
                {"error": "user_ids must be a non-empty list"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            users = UserProfile.objects.filter(
                id__in=user_ids, 
                is_deleted=False
            )
            
            if not users.exists():
                return Response(
                    {"error": "No active users found with provided IDs"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            updated_count = 0
            results = []
            
            for user in users:
                user.is_deleted = True
                user.is_active = False
                user.is_online = False
                user.is_loginned = False
                user.save()
                
                updated_count += 1
                results.append({
                    "id": user.id,
                    "user_id": user.user_id,
                    "name": user.name,
                    "email": user.email,
                    "status": "deleted"
                })
            
            return Response({
                "message": f"Bulk soft delete completed",
                "deleted_count": updated_count,
                "results": results,
                "reason": reason
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": f"An error occurred during bulk delete: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeletedUsersListView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]
    
    def get(self, request):
        queryset = UserProfile.objects.filter(is_deleted=True)
        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(user_id__icontains=search) |
                Q(mobile_number__icontains=search)
            )
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        queryset = queryset.order_by('-created_at')
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        paginated_queryset = queryset[start:end]
        
        serializer = UserProfileSerializer(paginated_queryset, many=True)
        
        return Response({
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "results": serializer.data
        }, status=status.HTTP_200_OK)


class UserDeletionStatsView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]
    
    def get(self, request):
        from datetime import timedelta
        
        total_users = UserProfile.objects.count()
        active_users = UserProfile.objects.filter(is_deleted=False, is_active=True).count()
        deleted_users = UserProfile.objects.filter(is_deleted=True).count()
        
        week_ago = timezone.now() - timedelta(days=7)
        recent_deletions = UserProfile.objects.filter(
            is_deleted=True,
            created_at__gte=week_ago  
        ).count()
        
        month_ago = timezone.now() - timedelta(days=30)
        monthly_deletions = UserProfile.objects.filter(
            is_deleted=True,
            created_at__gte=month_ago
        ).count()
        
        return Response({
            "total_users": total_users,
            "active_users": active_users,
            "deleted_users": deleted_users,
            "recent_deletions": recent_deletions,
            "monthly_deletions": monthly_deletions,
            "deletion_rate": round((deleted_users / total_users * 100) if total_users > 0 else 0, 2)
        }, status=status.HTTP_200_OK)


class UserAccountStatusView(APIView):
    permission_classes = [IsAuthenticated]    
    def get(self, request, user_id=None):
        try:
            if user_id and request.user.is_staff:
                user = get_object_or_404(UserProfile, id=user_id)
            else:
                user = request.user
            
            return Response({
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "is_active": user.is_active,
                "is_deleted": user.is_deleted,
                "is_suspended": user.is_suspended,
                "is_banned": user.is_banned,
                "is_online": user.is_online,
                "last_login": user.last_login
            }, status=status.HTTP_200_OK)
            
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
class FavoriteExecutiveView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        favorites = Favourite.objects.filter(user=request.user).select_related('executive')
        favorite_executives = [fav.executive for fav in favorites]

        serializer = ExecutiveFavoriteSerializer(
            favorite_executives,
            many=True,
            context={'request': request}
        )
        return Response({
            'success': True,
            'count': len(favorite_executives),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):

        exec_id = request.data.get('id')
        action = request.data.get('action', 'add')

        if not exec_id:
            return Response({'success': False, 'error': 'id is required'}, status=status.HTTP_400_BAD_REQUEST)

        if action not in ['add', 'remove']:
            return Response({'success': False, 'error': 'action must be either "add" or "remove"'}, status=status.HTTP_400_BAD_REQUEST)

        executive = get_object_or_404(Executive, id=exec_id, status='active')

        if action == 'add':
            favourite, created = Favourite.objects.get_or_create(user=request.user, executive=executive)
            if not created:
                return Response({'success': False, 'message': 'Executive is already in favorites'}, status=status.HTTP_400_BAD_REQUEST)

            serializer = ExecutiveFavoriteSerializer(executive, context={'request': request})
            return Response({'success': True, 'message': 'Executive added to favorites successfully', 'data': serializer.data}, status=status.HTTP_200_OK)

        else:  # remove
            deleted, _ = Favourite.objects.filter(user=request.user, executive=executive).delete()
            if not deleted:
                return Response({'success': False, 'message': 'Executive is not in favorites'}, status=status.HTTP_400_BAD_REQUEST)

            return Response({'success': True, 'message': 'Executive removed from favorites successfully'}, status=status.HTTP_200_OK)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

class ExecutiveRatingsAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes=[JWTAuthentication]  

    def get(self, request, executive_id):
        executive = get_object_or_404(Executive, id=executive_id)

        ratings = Rating.objects.filter(executive=executive).order_by("-created_at")
        serializer = RatingSerializer(ratings, many=True)

        return Response({
            "executive": executive.name,
            "total_ratings": ratings.count(),
            "average_rating": ratings.aggregate(avg=models.Avg("rating"))["avg"] or 0,
            "ratings": serializer.data
        }, status=status.HTTP_200_OK)