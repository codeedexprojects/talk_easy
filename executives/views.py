# views.py
from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import Max
from .models import Executive, ExecutiveStats
from .serializers import *
import re
from django.contrib.auth import authenticate
import random
from executives.utils import send_otp
from rest_framework.views import APIView
from executives.models import *
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAdminUser
# For admin-specific views
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from executives.authentication import ExecutiveTokenAuthentication



class LanguageListCreateView(generics.ListCreateAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

class LanguageListView(generics.ListAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = []

class LanguageDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]


def generate_executive_tokens(executive):
    refresh = RefreshToken.for_user(executive) 
    ExecutiveToken.objects.create(executive=executive, refresh_token=str(refresh))
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

def generate_executive_id():
    last_id = Executive.objects.aggregate(max_id=Max('executive_id'))['max_id']
    if last_id:
        number = int(re.sub(r'\D', '', last_id)) + 1
    else:
        number = 1
    return f"TEY{str(number).zfill(4)}"  # TEY00001


from rest_framework.exceptions import ValidationError

class RegisterExecutiveView(generics.CreateAPIView):
    permission_classes = []
    queryset = Executive.objects.all()
    serializer_class = ExecutiveSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['executive_id'] = generate_executive_id()

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            error_messages = []
            for field, messages in e.detail.items():
                error_messages.append(f"{' '.join(messages)}")

            return Response(
                {
                    "message": " ".join(error_messages)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        executive = serializer.save()
        ExecutiveStats.objects.create(executive=executive)

        return Response(
            {
                "message": "Registration completed, the account will be verified within 24 hours.",
                "executive": ExecutiveSerializer(executive).data
            },
            status=status.HTTP_201_CREATED
        )



from django.contrib.auth.hashers import check_password
from django.core.cache import cache
class ExecutiveLoginView(APIView):
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        password = request.data.get("password")

        if not mobile_number or not password:
            return Response(
                {"message": "Mobile number and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            executive = Executive.objects.get(mobile_number=mobile_number)
        except Executive.DoesNotExist:
            return Response({"message": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)

        if not check_password(password, executive.password):
            return Response({"message": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED)

        if executive.online and not executive.is_logged_out:
            return Response(
                {"message": "Already logged in on another device. Please logout first."},
                status=status.HTTP_403_FORBIDDEN
            )

        if executive.is_suspended or executive.is_banned:
            return Response(
                {"message": "Your account is suspended or banned. Contact admin."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not executive.is_verified:
            return Response(
                {"message": "Your account is not verified by admin yet."},
                status=status.HTTP_403_FORBIDDEN
            )

        otp = str(random.randint(100000, 999999))
        executive.otp = otp
        executive.is_verified = True 
        executive.save(update_fields=["otp", "is_verified"])

        if not send_otp(mobile_number, otp):
            return Response({"message": "Failed to send OTP"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "message": "Password verified. OTP sent to your mobile. Please verify to complete login.",
            "status": True,
            "otp":executive.otp
        }, status=status.HTTP_200_OK)



from rest_framework_simplejwt.tokens import RefreshToken

class ExecutiveVerifyOTPView(APIView):
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        otp = request.data.get("otp")

        try:
            executive = Executive.objects.get(mobile_number=mobile_number)
        except Executive.DoesNotExist:
            return Response({"message": "Executive not found"}, status=status.HTTP_404_NOT_FOUND)

        if not executive.otp or str(executive.otp) != str(otp):
            return Response({"message": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        executive.otp = None
        executive.is_verified = True
        executive.online = True
        executive.is_logged_out = False
        executive.save(update_fields=["otp", "is_verified", "online", "is_logged_out"])

        token_obj = ExecutiveToken.generate(executive)

        return Response({
            "message": "OTP verified successfully",
            "executive_id":executive.executive_id,
            "id":executive.id,
            "name":executive.name,
            "access_token": token_obj.access_token,
            "refresh_token": token_obj.refresh_token,
            "expires_at": token_obj.expires_at
        }, status=status.HTTP_200_OK)
    

from rest_framework.permissions import IsAuthenticated

class ExecutiveLogoutView(APIView):
    permission_classes = []

    def post(self, request, executive_id):
        refresh_token = request.data.get("refresh_token")

        if not refresh_token:
            return Response({"message": "refresh_token is required."}, status=400)

        try:
            token_obj = ExecutiveToken.objects.get(refresh_token=refresh_token, executive_id=executive_id)
            token_obj.revoked = True
            token_obj.revoked_at = timezone.now()
            token_obj.save()
        except ExecutiveToken.DoesNotExist:
            return Response({"message": "Token not found or already revoked."}, status=404)

        # Update executive status if needed
        Executive.objects.filter(id=executive_id).update(online=False, is_logged_out=True)

        return Response({"message": "Logout successful."}, status=200)

from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.authentication import JWTAuthentication
from accounts.pagination import CustomExecutivePagination
from rest_framework.generics import ListAPIView

class ExecutiveListAPIView(ListAPIView):
    serializer_class = ExecutiveSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomExecutivePagination

    def get_queryset(self):
        return Executive.objects.filter(is_verified=True).order_by("-id")


class ExecutiveDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication] 

    def get(self, request, id):
        executive = get_object_or_404(Executive, id=id)
        serializer = ExecutiveSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class ExecutiveUpdateByIDAPIView(APIView):
    permission_classes = [IsAuthenticated] 

    def put(self, request, id):
        return self.update_executive(request, id)

    def patch(self, request, id):
        return self.update_executive(request, id, partial=True)

    def update_executive(self, request, id, partial=False):
        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveSerializer(executive, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class AdminUpdateExecutiveAPIView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]

    def get(self, request, id):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id):
        return self.update_executive(request, id)

    def patch(self, request, id):
        return self.update_executive(request, id, partial=True)

    def update_executive(self, request, id, partial=False):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveSerializer(executive, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    
from users.models import UserProfile

class BlockUserAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        executive = request.user 

        try:
            user = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        obj, created = BlockedusersByExecutive.objects.update_or_create(
            user=user,
            executive=executive,
            defaults={'is_blocked': True, 'reason': 'Blocked by executive'}
        )
        return Response(
            {"detail": f"User {user_id} blocked by Executive {executive.executive_id} successfully.", "status": True},
            status=status.HTTP_200_OK
        )


class UnblockUserAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        executive = request.user 

        try:
            blocked_entry = BlockedusersByExecutive.objects.get(user_id=user_id, executive=executive)
            blocked_entry.is_blocked = False
            blocked_entry.save(update_fields=['is_blocked'])
            return Response(
                {"detail": f"User {user_id} unblocked by Executive {executive.executive_id} successfully.", "status": True},
                status=status.HTTP_200_OK
            )
        except BlockedusersByExecutive.DoesNotExist:
            return Response(
                {"detail": "This user is not blocked by you.", "status": False},
                status=status.HTTP_404_NOT_FOUND
            )
        
class UpdateExecutiveStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]  
    authentication_classes = [JWTAuthentication]


    def patch(self, request, executive_id):
        user = request.user
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
            return Response({"detail": "Not authorized.", "status": False}, status=status.HTTP_403_FORBIDDEN)

        try:
            executive = Executive.objects.get(id=executive_id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found.", "status": False}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveStatusUpdateSerializer(executive, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Executive status updated successfully.", "status": True}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UpdateExecutiveOnlineStatusAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication] 
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        executive = request.user

        serializer = ExecutiveOnlineStatusSerializer(executive, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "detail": "Status updated successfully.",
                "status": True,
                "is_online": executive.is_online,
                "is_offline": executive.is_offline,
                "executive_id":executive.executive_id,
                "id": executive.id

            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    


class ExecutiveSuspendToggleView(APIView):
    authentication_classes = [JWTAuthentication]  
    permission_classes = [IsAdminUser]

    def post(self, request, id): 
        try:
            executive = Executive.objects.get(id=id) 
        except Executive.DoesNotExist:
            return Response({"error": "Executive not found"}, status=404)
        executive.is_suspended = not executive.is_suspended
        executive.save()

        status_text = "suspended" if executive.is_suspended else "unsuspended"
        return Response(
            {
                "id": executive.id,
                "name": executive.name,
                "is_suspended": executive.is_suspended,
                "message": f"Executive has been {status_text} successfully."
            },
            status=status.HTTP_200_OK
        )
    
class ExecutiveProfilePictureUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, executive_id=None):
        try:
            if executive_id:
                executive = get_object_or_404(Executive, id=executive_id)
            else:
                executive = get_object_or_404(Executive, user=request.user)  
            
            profile_picture, created = ExecutiveProfilePicture.objects.get_or_create(
                executive=executive,
                defaults={'status': 'pending'}
            )
            
            if not created:
                profile_picture.status = 'pending'            
            if 'profile_photo' not in request.FILES:
                return Response(
                    {"error": "No profile photo provided"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            profile_picture.profile_photo = request.FILES['profile_photo']
            profile_picture.save()
            
            serializer = ExecutiveProfilePictureSerializer(profile_picture)
            
            return Response({
                "message": "Profile picture uploaded successfully. Status: Pending approval.",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
            
        except Executive.DoesNotExist:
            return Response(
                {"error": "Executive not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request, executive_id=None):
        try:
            if executive_id:
                executive = get_object_or_404(Executive, id=executive_id)
            else:
                executive = get_object_or_404(Executive, user=request.user)  
            
            try:
                profile_picture = ExecutiveProfilePicture.objects.get(executive=executive)
                serializer = ExecutiveProfilePictureSerializer(profile_picture)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except ExecutiveProfilePicture.DoesNotExist:
                return Response(
                    {"message": "No profile picture found for this executive"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
                
        except Executive.DoesNotExist:
            return Response(
                {"error": "Executive not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class ExecutiveProfilePictureStatusView(APIView):
    permission_classes = [IsAuthenticated]  
    def get(self, request, executive_id=None):

        try:
            if executive_id:
                executive = get_object_or_404(Executive, id=executive_id)
            else:
                executive = get_object_or_404(Executive, user=request.user)
            
            try:
                profile_picture = ExecutiveProfilePicture.objects.get(executive=executive)
                return Response({
                    "status": profile_picture.status,
                    "created_at": profile_picture.created_at,
                    "updated_at": profile_picture.updated_at
                }, status=status.HTTP_200_OK)
            except ExecutiveProfilePicture.DoesNotExist:
                return Response({
                    "status": "not_uploaded",
                    "message": "No profile picture uploaded yet"
                }, status=status.HTTP_200_OK)
                
        except Executive.DoesNotExist:
            return Response(
                {"error": "Executive not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
from django.db.models import Q      
class AdminProfilePictureListView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication] 
    
    def get(self, request):
        queryset = ExecutiveProfilePicture.objects.select_related('executive').all()        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)        
        executive_id = request.query_params.get('executive_id')
        if executive_id:
            queryset = queryset.filter(executive_id=executive_id)        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(executive__name__icontains=search) |
                Q(executive__email__icontains=search)
            )        
        queryset = queryset.order_by('-created_at')
        
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 20)
        
        try:
            page = int(page)
            page_size = int(page_size)
            start = (page - 1) * page_size
            end = start + page_size
            
            total_count = queryset.count()
            paginated_queryset = queryset[start:end]
            
            serializer = ExecutiveProfilePictureSerializer(
                paginated_queryset, 
                many=True, 
                context={'request': request}
            )
            
            return Response({
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size,
                "results": serializer.data
            }, status=status.HTTP_200_OK)
            
        except ValueError:
            return Response(
                {"error": "Invalid page or page_size parameter"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
class AdminProfilePictureDetailView(APIView):
    authentication_classes = [JWTAuthentication]  
    permission_classes = [IsAdminUser]    
    def get(self, request, picture_id):
        try:
            profile_picture = ExecutiveProfilePicture.objects.select_related('executive').get(id=picture_id)
            serializer = ExecutiveProfilePictureSerializer(profile_picture, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ExecutiveProfilePicture.DoesNotExist:
            return Response(
                {"error": "Profile picture not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AdminProfilePictureApproveView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]   
    def post(self, request, picture_id):
        try:
            profile_picture = ExecutiveProfilePicture.objects.get(id=picture_id)
            
            if profile_picture.status == 'approved':
                return Response(
                    {"message": "Profile picture is already approved"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            profile_picture.approve()
            
            serializer = ExecutiveProfilePictureSerializer(profile_picture, context={'request': request})
            
            return Response({
                "message": "Profile picture approved successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except ExecutiveProfilePicture.DoesNotExist:
            return Response(
                {"error": "Profile picture not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AdminProfilePictureRejectView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    
    def post(self, request, picture_id):
        serializer = AdminProfilePictureActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            profile_picture = ExecutiveProfilePicture.objects.get(id=picture_id)
            
            if profile_picture.status == 'rejected':
                return Response(
                    {"message": "Profile picture is already rejected"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            profile_picture.reject()            
            serializer_response = ExecutiveProfilePictureSerializer(profile_picture, context={'request': request})
            
            return Response({
                "message": "Profile picture rejected successfully",
                "data": serializer_response.data,
                "reason": serializer.validated_data.get('reason', '')
            }, status=status.HTTP_200_OK)
            
        except ExecutiveProfilePicture.DoesNotExist:
            return Response(
                {"error": "Profile picture not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class AdminProfilePictureBulkActionView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    
    def post(self, request):
        action = request.data.get('action')
        picture_ids = request.data.get('picture_ids', [])
        reason = request.data.get('reason', '')
        
        if action not in ['approve', 'reject']:
            return Response(
                {"error": "Action must be either 'approve' or 'reject'"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not picture_ids or not isinstance(picture_ids, list):
            return Response(
                {"error": "picture_ids must be a non-empty list"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            profile_pictures = ExecutiveProfilePicture.objects.filter(id__in=picture_ids)
            
            if not profile_pictures.exists():
                return Response(
                    {"error": "No profile pictures found with provided IDs"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            updated_count = 0
            results = []
            
            for picture in profile_pictures:
                if action == 'approve' and picture.status != 'approved':
                    picture.approve()
                    updated_count += 1
                    results.append({
                        "id": picture.id,
                        "executive": picture.executive.name,
                        "status": "approved",
                        "message": "Approved successfully"
                    })
                elif action == 'reject' and picture.status != 'rejected':
                    picture.reject()
                    updated_count += 1
                    results.append({
                        "id": picture.id,
                        "executive": picture.executive.name,
                        "status": "rejected",
                        "message": "Rejected successfully",
                        "reason": reason
                    })
                else:
                    results.append({
                        "id": picture.id,
                        "executive": picture.executive.name,
                        "status": picture.status,
                        "message": f"Already {picture.status}"
                    })
            
            return Response({
                "message": f"Bulk {action} completed",
                "updated_count": updated_count,
                "total_processed": len(results),
                "results": results
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": f"An error occurred during bulk action: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminProfilePictureStatsView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication]  
    
    def get(self, request):
        total = ExecutiveProfilePicture.objects.count()
        pending = ExecutiveProfilePicture.objects.filter(status='pending').count()
        approved = ExecutiveProfilePicture.objects.filter(status='approved').count()
        rejected = ExecutiveProfilePicture.objects.filter(status='rejected').count()
        
        from django.utils import timezone
        from datetime import timedelta
        
        week_ago = timezone.now() - timedelta(days=7)
        recent = ExecutiveProfilePicture.objects.filter(created_at__gte=week_ago).count()
        
        return Response({
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "recent_submissions": recent,
            "approval_rate": round((approved / total * 100) if total > 0 else 0, 2)
        }, status=status.HTTP_200_OK)
    
class ExecutiveStatusAPIView(APIView):
    authentication_classes = [ExecutiveTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        executive = request.user 
        serializer = ExecutiveDetailSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class ExecutiveStatsDetailView(APIView):
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication] 
    def get(self, request, id):
        executive = get_object_or_404(Executive, id=id)

        stats, _ = ExecutiveStats.objects.get_or_create(executive=executive)

        serializer = ExecutiveStatsSerializer(stats)
        return Response(serializer.data, status=status.HTTP_200_OK)