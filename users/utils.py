from datetime import datetime, timedelta, timezone
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import UserProfileOutstandingToken, UserProfileBlacklistedToken

class UserProfileRefreshToken(RefreshToken):
    
    @classmethod
    def for_user(cls, user):
        token = cls()
        token['user_id'] = user.id
        return token

def create_tokens_for_userprofile(user):
    refresh = UserProfileRefreshToken.for_user(user)
    
    jti = refresh['jti']
    expires_at = datetime.fromtimestamp(refresh['exp'], tz=timezone.utc)
    
    UserProfileOutstandingToken.objects.create(
        user=user,
        jti=jti,
        token=str(refresh),
        expires_at=expires_at,
    )
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

def is_token_blacklisted(jti):
    return UserProfileBlacklistedToken.objects.filter(token__jti=jti).exists()

def blacklist_token(token_str):
    try:
        outstanding_token = UserProfileOutstandingToken.objects.get(token=token_str)
        UserProfileBlacklistedToken.objects.get_or_create(token=outstanding_token)
    except UserProfileOutstandingToken.DoesNotExist:
        pass

def cleanup_expired_tokens():
    from django.utils import timezone
    expired_tokens = UserProfileOutstandingToken.objects.filter(
        expires_at__lt=timezone.now()
    )
    expired_tokens.delete()