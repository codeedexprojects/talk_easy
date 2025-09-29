import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from django.utils import timezone
from urllib.parse import parse_qs

# JWT imports for UsersConsumer
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
import jwt

# Import your models (adjust paths as needed)
from executives.models import Executive, ExecutiveToken
from users.models import UserProfile

# Clean global dictionary for executive statuses
EXECUTIVE_STATUS = {}

class JWTAuthMixin:
    
    async def authenticate_jwt(self, token):
        try:
            UntypedToken(token)
            
            decoded_token = jwt.decode(
                token, 
                settings.SECRET_KEY, 
                algorithms=['HS256']
            )
            
            user_id = decoded_token.get('user_id')
            print(f"DEBUG: JWT Token decoded user_id: {user_id}")  
            
            if not user_id:
                return None
                
            user = await self.get_user_by_id_jwt(user_id)
            if user:
                print(f"DEBUG: Found user via JWT: {getattr(user, 'name', 'Unknown')} (ID: {user.id})")
            return user
            
        except (InvalidToken, TokenError, jwt.ExpiredSignatureError, jwt.DecodeError) as e:
            print(f"JWT Authentication failed: {str(e)}")
            return None
    
    @database_sync_to_async
    def get_user_by_id_jwt(self, user_id):
        try:
            executive = Executive.objects.get(id=user_id)
            print(f"DEBUG: Found executive via JWT: {executive.name} ({executive.executive_id})")
            return executive
        except Executive.DoesNotExist:
            try:
                user_profile = UserProfile.objects.get(id=user_id)
                print(f"DEBUG: Found UserProfile via JWT: {getattr(user_profile, 'name', 'Unknown User')}")
                return user_profile
            except UserProfile.DoesNotExist:
                return None


class CustomTokenAuthMixin:    
    async def authenticate_token(self, token):
        try:
            token_obj = await self.get_token_by_refresh_token(token)
            if not token_obj:
                print(f"DEBUG: Token not found in database: {token[:10]}...")
                return None
            
            if hasattr(token_obj, 'expires_at') and token_obj.expires_at:
                if token_obj.expires_at < timezone.now():
                    print(f"DEBUG: Token expired at {token_obj.expires_at}")
                    return None
            
            executive = token_obj.executive
            if executive:
                print(f"DEBUG: Found executive: {executive.name} (ID: {executive.id}, Exec ID: {executive.executive_id})")
            return executive
            
        except Exception as e:
            print(f"Custom Token Authentication failed: {str(e)}")
            return None
    
    @database_sync_to_async
    def get_token_by_refresh_token(self, token):
        try:
            return ExecutiveToken.objects.select_related('executive').get(refresh_token=token)
        except ExecutiveToken.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_user_by_id(self, user_id):
        try:
            executive = Executive.objects.get(id=user_id)
            print(f"DEBUG: Found executive: {executive.name} ({executive.executive_id})")
            return executive
        except Executive.DoesNotExist:
            try:
                return UserProfile.objects.get(id=user_id)
            except UserProfile.DoesNotExist:
                return None


class ExecutivesConsumer(AsyncWebsocketConsumer, CustomTokenAuthMixin):
    async def connect(self):
        headers = dict(self.scope.get('headers', []))
        token = headers.get(b'x-executive-token', b'').decode()
        
        if not token:
            query_string = self.scope.get('query_string', b'').decode()
            query_params = parse_qs(query_string)
            token = query_params.get('token', [None])[0]
        
        if not token:
            print("DEBUG: No token provided in headers or query params")
            await self.close(code=4001)
            return
        
        # Authenticate user with custom token
        authenticated_user = await self.authenticate_token(token)
        if not authenticated_user:
            print("DEBUG: Authentication failed")
            # Send error message before closing
            await self.accept()
            await self.send(text_data=json.dumps({
                "type": "authentication_error",
                "error": "Authentication failed. Token may be expired or invalid.",
                "code": 4001
            }))
            await self.close(code=4001)
            return
        
        if not isinstance(authenticated_user, Executive):
            print("DEBUG: User is not an Executive")
            await self.close(code=4003)
            return
        
        self.user = authenticated_user
        
        path_executive_id = self.scope['url_route']['kwargs'].get('executive_id')
        
        if path_executive_id and str(path_executive_id) != str(self.user.executive_id):
            print(f"DEBUG: Access denied. Path ID: {path_executive_id}, User ID: {self.user.executive_id}")
            await self.close(code=4003)
            return
        
        # Use the authenticated user's executive_id
        self.executive_id = str(self.user.executive_id)
        self.users_group_name = "users_online"
        
        print(f"DEBUG: Executive {self.user.name} ({self.executive_id}) connecting...")
        
        await self.accept()
        
        await self.channel_layer.group_add(self.users_group_name, self.channel_name)
        
        EXECUTIVE_STATUS[self.executive_id] = "online"
        
        await self.update_executive_status("online")
        
        await self.broadcast_status()
        
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "executive_id": self.executive_id,
            "name": self.user.name,
            "status": "online",
            "message": "Successfully connected",
            "debug_info": {
                "user_primary_key": self.user.id,
                "executive_id_field": self.user.executive_id,
                "mobile_number": self.user.mobile_number
            }
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "executive_id") and hasattr(self, "user"):
            print(f"DEBUG: Executive {self.user.name} ({self.executive_id}) disconnecting...")
            EXECUTIVE_STATUS[self.executive_id] = "offline"
            await self.update_executive_status("offline")
            await self.broadcast_status()
        
        if hasattr(self, "users_group_name") and hasattr(self, "channel_name"):
            await self.channel_layer.group_discard(self.users_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            print(f"DEBUG: Received message from {self.user.name}: {data}")
            
            if "status" in data:
                new_status = data["status"]
                
                valid_statuses = ["online", "offline", "oncall"]
                if new_status not in valid_statuses:
                    await self.send(text_data=json.dumps({
                        "error": f"Invalid status. Valid options: {valid_statuses}"
                    }))
                    return
                
                EXECUTIVE_STATUS[self.executive_id] = new_status
                await self.update_executive_status(new_status)
                await self.broadcast_status()
                
            elif "connect" in data:
                status = "online" if data["connect"] else "offline"
                EXECUTIVE_STATUS[self.executive_id] = status
                await self.update_executive_status(status)
                await self.broadcast_status()
                
            elif "oncall" in data:
                status = "oncall" if data["oncall"] else "online"
                EXECUTIVE_STATUS[self.executive_id] = status
                await self.update_executive_status(status)
                await self.broadcast_status()
            
            await self.send(text_data=json.dumps({
                "type": "ack",
                "executive_id": self.executive_id,
                "status": EXECUTIVE_STATUS[self.executive_id],
                "message": f"Status updated to {EXECUTIVE_STATUS[self.executive_id]}"
            }))
            
        except Exception as e:
            print(f"DEBUG: Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({"error": str(e)}))

    @database_sync_to_async
    def update_executive_status(self, status):
        try:
            self.user.is_online = status == "online"
            self.user.on_call = status == "oncall"
            self.user.save(update_fields=['is_online', 'on_call'])
            print(f"DEBUG: Updated {self.user.name} status in database: {status}")
        except Exception as e:
            print(f"DEBUG: Error updating database: {str(e)}")

    async def broadcast_status(self):
        try:
            executive_data = await self.get_executives_detailed_status()
            
            print(f"DEBUG: Broadcasting status update: {len(executive_data)} executives")
            
            await self.channel_layer.group_send(
                self.users_group_name,
                {
                    "type": "status_update",
                    "data": executive_data
                }
            )
        except Exception as e:
            print(f"DEBUG: Error in broadcast_status: {str(e)}")

    @database_sync_to_async
    def get_executives_detailed_status(self):
        executive_data = []
        for exec_id, status in EXECUTIVE_STATUS.items():
            try:
                executive = Executive.objects.get(executive_id=exec_id)
                executive_data.append({
                    "executive_id": exec_id,
                    "name": executive.name,
                    "status": status,
                    "is_available": status in ["online", "oncall"]
                })
                print(f"DEBUG: Added {executive.name} to status list")
            except Executive.DoesNotExist:
                print(f"DEBUG: Executive with ID {exec_id} not found in database")
                # If executive not found, include basic info
                executive_data.append({
                    "executive_id": exec_id,
                    "name": "Unknown Executive",
                    "status": status,
                    "is_available": False
                })
        return executive_data

    async def status_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                "type": "executive_status_list",
                "data": event["data"]
            }))
        except Exception:
            pass


class UsersConsumer(AsyncWebsocketConsumer, JWTAuthMixin):
    
    async def connect(self):
        # Extract token from headers first, fallback to query parameters
        headers = dict(self.scope.get('headers', []))
        token = headers.get(b'authorization', b'').decode().replace('Bearer ', '')
        
        # Fallback to query parameters if no header token
        if not token:
            query_string = self.scope.get('query_string', b'').decode()
            query_params = parse_qs(query_string)
            token = query_params.get('token', [None])[0]
        
        if not token:
            print("DEBUG: No JWT token provided in headers or query params")
            await self.close(code=4001)
            return
        
        # Authenticate user with JWT
        authenticated_user = await self.authenticate_jwt(token)
        if not authenticated_user:
            print("DEBUG: JWT authentication failed")
            await self.close(code=4001)
            return
        
        self.user = authenticated_user
        self.group_name = "users_online"
        
        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        
        executive_data = await self.get_executives_detailed_status()
        await self.send(text_data=json.dumps({
            "type": "executive_status_list",
            "data": executive_data,
            "user_info": {
                "user_id": getattr(self.user, 'user_id', None) or getattr(self.user, 'executive_id', None),
                "name": getattr(self.user, 'name', 'Unknown'),
                "user_type": "executive" if isinstance(self.user, Executive) else "user"
            }
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name') and hasattr(self, 'channel_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def get_executives_detailed_status(self):
        executive_data = []
        for exec_id, status in EXECUTIVE_STATUS.items():
            try:
                executive = Executive.objects.get(executive_id=exec_id)
                executive_data.append({
                    "executive_id": exec_id,
                    "name": executive.name,
                    "status": status,
                    "is_available": status in ["online", "oncall"]
                })
            except Executive.DoesNotExist:
                executive_data.append({
                    "executive_id": exec_id,
                    "name": "Unknown Executive",
                    "status": status,
                    "is_available": False
                })
        return executive_data

    async def status_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "executive_status_list",
            "data": event["data"]
        }))