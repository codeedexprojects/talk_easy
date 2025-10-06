import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from urllib.parse import parse_qs
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth.models import AnonymousUser

User = get_user_model()

def JWTAuthMiddleware(inner):
    class JWTAuthMiddlewareImpl(BaseMiddleware):
        def __init__(self, inner):
            super().__init__(inner)

        async def __call__(self, scope, receive, send):
            # Default to anonymous user
            scope['user'] = AnonymousUser()
            
            # Extract token from query parameters
            token = self.get_token_from_scope(scope)
            
            if token:
                try:
                    # Validate token using SimpleJWT
                    UntypedToken(token)
                    
                    # Decode to get user info
                    decoded_token = jwt.decode(
                        token,
                        settings.SECRET_KEY,
                        algorithms=['HS256']
                    )
                    
                    user_id = decoded_token.get('user_id')
                    
                    if user_id:
                        user = await self.get_user(user_id)
                        if user:
                            scope['user'] = user
                   
                except (InvalidToken, TokenError, jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                    # Token is invalid, keep anonymous user
                    pass
                except Exception:
                    # Any other error, keep anonymous user
                    pass
            
            return await super().__call__(scope, receive, send)

        def get_token_from_scope(self, scope):
            """Extract JWT token from WebSocket connection"""
            try:
                query_string = scope.get('query_string', b'').decode()
                query_params = parse_qs(query_string)
                
                if 'token' in query_params:
                    return query_params['token'][0]
            except Exception:
                pass
            
            return None

        @database_sync_to_async
        def get_user(self, user_id):
            """Get user from database"""
            try:
                return User.objects.get(id=user_id)
            except User.DoesNotExist:
                return None
            except Exception:
                return None

    return JWTAuthMiddlewareImpl(inner)