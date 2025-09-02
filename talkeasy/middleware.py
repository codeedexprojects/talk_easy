# middleware.py (create this file in your project root or app directory)
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs
import jwt
from django.conf import settings
from users.models import UserProfile
from django.contrib.auth import get_user_model


@database_sync_to_async
def get_user_from_token(token):
    try:
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        
        # Validate token format
        UntypedToken(token)
        
        # Decode token
        decoded_data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = decoded_data.get('user_id')
        
        if user_id:
            # Try UserProfile first
            try:
                user = UserProfile.objects.get(id=user_id)
                return user
            except UserProfile.DoesNotExist:
                # Fallback to default User model
                User = get_user_model()
                try:
                    user = User.objects.get(id=user_id)
                    return user
                except User.DoesNotExist:
                    return None
        return None
        
    except (InvalidToken, TokenError, jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception) as e:
        print(f"Token validation error: {e}")
        return None


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware to authenticate WebSocket connections using JWT tokens
    """
    
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        # Only process WebSocket connections
        if scope["type"] == "websocket":
            # Get token from query string
            query_string = scope.get("query_string", b"").decode()
            query_params = parse_qs(query_string)
            token = query_params.get("token", [None])[0]
            
            if token:
                # Authenticate user
                user = await get_user_from_token(token)
                if user:
                    scope["user"] = user
                else:
                    scope["user"] = AnonymousUser()
            else:
                scope["user"] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)