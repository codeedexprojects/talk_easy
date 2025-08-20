from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from users.models import UserProfile
from users.utils import is_token_blacklisted

class UserProfileJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user_id = validated_token.get('user_id')
        if not user_id:
            raise InvalidToken('Token contained no recognizable user identification')

        try:
            return UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            raise InvalidToken('User not found')

    def authenticate(self, request):
        auth = super().authenticate(request)
        if auth is None:
            return None

        user, validated_token = auth

        # Check blacklist manually
        jti = validated_token.get('jti')
        if is_token_blacklisted(jti):
            raise InvalidToken('Token is blacklisted')

        return (user, validated_token)