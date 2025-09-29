from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import ExecutiveToken
from django.utils import timezone


class ExecutiveTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.headers.get("X-EXECUTIVE-TOKEN")
        if not token:
            return None

        try:
            token_obj = ExecutiveToken.objects.get(refresh_token=token)  
        except ExecutiveToken.DoesNotExist:
            raise AuthenticationFailed("Invalid token")

        if hasattr(token_obj, "expires_at") and token_obj.expires_at < timezone.now():
            raise AuthenticationFailed("Token expired")

        return (token_obj.executive, None)
