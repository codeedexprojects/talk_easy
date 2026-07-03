from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import ExecutiveToken
from django.utils import timezone

class ExecutiveTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.headers.get("X-EXECUTIVE-TOKEN")
        if not token:
            return None  # no token provided

        try:
            token_obj = ExecutiveToken.objects.get(access_token=token)
        except ExecutiveToken.DoesNotExist:
            raise AuthenticationFailed("Invalid or missing token")

        if token_obj.executive.is_banned:
            raise AuthenticationFailed("Your account has been banned by admin.")

        if token_obj.revoked:
            raise AuthenticationFailed("Token revoked")

        if token_obj.expires_at < timezone.now():
            raise AuthenticationFailed("Token expired")

        return (token_obj.executive, None)


from rest_framework.views import exception_handler
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None and isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        response.status_code = 403
        detail = exc.detail if hasattr(exc, "detail") else str(exc)
        response.data = {"message": str(detail)}

    return response
