# views.py
from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import Max
from .models import Executive, ExecutiveStats
from .serializers import *
import re
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
import random
from executives.utils import send_otp
from rest_framework.views import APIView
from executives.models import *
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework.permissions import IsAdminUser

def generate_executive_tokens(executive):
    refresh = RefreshToken.for_user(executive)  # You might need to customize this if it errors
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


class RegisterExecutiveView(generics.CreateAPIView):
    permission_classes = []
    queryset = Executive.objects.all()
    serializer_class = ExecutiveSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        
        data['executive_id'] = generate_executive_id()

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        executive = serializer.save()

        ExecutiveStats.objects.create(executive=executive)

        return Response(
            {
                "message": "Executive registered successfully",
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

        # Generate a 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Store OTP in DB instead of cache
        executive.otp = otp
        executive.is_verified = False
        executive.save(update_fields=["otp", "is_verified"])

        # Send OTP
        if not send_otp(mobile_number, otp):
            return Response({"message": "Failed to send OTP"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "message": "Password verified. OTP sent to your mobile. Please verify to complete login.",
            "status": True
        }, status=status.HTTP_200_OK)

from rest_framework_simplejwt.tokens import RefreshToken

class ExecutiveVerifyOTPView(APIView):
    permission_classes = []

    def post(self, request):
        mobile_number = request.data.get("mobile_number")
        otp = request.data.get("otp")

        if not mobile_number or not otp:
            return Response(
                {"message": "Mobile number and OTP are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            executive = Executive.objects.get(mobile_number=mobile_number, otp=otp)
        except Executive.DoesNotExist:
            return Response({"message": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        executive.otp = None
        executive.online = True
        executive.is_logged_out = False
        executive.save(update_fields=["otp", "online", "is_logged_out"])

        # Use linked Admin user for JWT tokens
        admin_user = executive.manager_executive
        if not admin_user:
            return Response(
                {"message": "Associated admin user not found."},
                status=status.HTTP_400_BAD_REQUEST
            )

        refresh = RefreshToken.for_user(admin_user)
        access_token = str(refresh.access_token)

        return Response({
            "message": "OTP verified successfully.",
            "id": executive.id,
            "executive_id": executive.executive_id,
            "name": executive.name,
            "status": True,
            "online": executive.online,
            "auto_logout_minutes": getattr(executive, "AUTO_LOGOUT_MINUTES", None),
            "access_token": access_token,
            "refresh_token": str(refresh)
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
    queryset = Executive.objects.all()
    serializer_class = ExecutiveSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    pagination_class = CustomExecutivePagination


class ExecutiveDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication] 

    def get(self, request, id):
        executive = get_object_or_404(Executive, id=id)
        serializer = ExecutiveSerializer(executive)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class ExecutiveUpdateByIDAPIView(APIView):
    permission_classes = [IsAuthenticated]  # Only authenticated users

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def post(self, request, executive_id, user_id):
        try:
            executive = Executive.objects.get(id=executive_id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found."}, status=status.HTTP_404_NOT_FOUND)

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
            {"detail": f"User {user_id} blocked by Executive {executive_id} successfully.","status":True},
            status=status.HTTP_200_OK
        )


class UnblockUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, executive_id, user_id):
        try:
            blocked_entry = BlockedusersByExecutive.objects.get(user_id=user_id, executive_id=executive_id)
            blocked_entry.is_blocked = False
            blocked_entry.save(update_fields=['is_blocked'])
            return Response(
                {"detail": f"User {user_id} unblocked by Executive {executive_id} successfully.","status":True},
                status=status.HTTP_200_OK
            )
        except BlockedusersByExecutive.DoesNotExist:
            return Response(
                {"detail": "This user is not blocked by this executive.","status":False},
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
    permission_classes = [IsAuthenticated]  

    def patch(self, request, id):
        try:
            executive = Executive.objects.get(id=id)
        except Executive.DoesNotExist:
            return Response({"detail": "Executive not found.", "status": False}, status=status.HTTP_404_NOT_FOUND)

        serializer = ExecutiveOnlineStatusSerializer(executive, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Status updated successfully.", "status": True}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ExecutiveSuspendToggleView(APIView):
    permission_classes = [IsAuthenticated]  
    def post(self, request, id):
        executive = get_object_or_404(Executive, id=id)        
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