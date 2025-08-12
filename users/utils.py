from datetime import datetime, timedelta, timezone
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import UserProfileOutstandingToken, UserProfileBlacklistedToken

class UserProfileRefreshToken(RefreshToken):
    """Custom RefreshToken for UserProfile model"""
    
    @classmethod
    def for_user(cls, user):
        """
        Returns an authorization token for the given UserProfile instance.
        """
        token = cls()
        token['user_id'] = user.id
        return token

def create_tokens_for_userprofile(user):
    """Create tokens for UserProfile instance"""
    refresh = UserProfileRefreshToken.for_user(user)
    
    # Save outstanding token info for refresh token
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
    """Check if a token is blacklisted"""
    return UserProfileBlacklistedToken.objects.filter(token__jti=jti).exists()

def blacklist_token(token_str):
    """Blacklist a token"""
    try:
        outstanding_token = UserProfileOutstandingToken.objects.get(token=token_str)
        UserProfileBlacklistedToken.objects.get_or_create(token=outstanding_token)
    except UserProfileOutstandingToken.DoesNotExist:
        pass

def cleanup_expired_tokens():
    """Clean up expired tokens (call this periodically)"""
    from django.utils import timezone
    expired_tokens = UserProfileOutstandingToken.objects.filter(
        expires_at__lt=timezone.now()
    )
    expired_tokens.delete()