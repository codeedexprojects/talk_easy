
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.serializers import *
from rest_framework import generics

class SuperuserLoginView(generics.GenericAPIView):
    serializer_class = SuperuserLoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        admin = authenticate(request, email=email, password=password)

        if not admin:
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        if not admin.is_superuser:
            return Response({"detail": "Only superusers can log in here."}, status=status.HTTP_403_FORBIDDEN)

        if getattr(admin, "role", None) != "superuser":
            admin.role = "superuser"
            admin.save(update_fields=["role"])

        refresh = RefreshToken.for_user(admin)

        return Response({
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "user_id": admin.id,
            "email": admin.email,
            "role": admin.role,
            "is_superuser": admin.is_superuser,
            "is_staff": admin.is_staff,
        }, status=status.HTTP_200_OK)
