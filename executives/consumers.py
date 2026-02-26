import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from django.conf import settings

from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import jwt

from executives.models import Executive, ExecutiveToken
from users.models import UserProfile

logger = logging.getLogger("executives")

EXECUTIVE_STATUS = {}


# -------------------- JWT Auth Mixin --------------------
class JWTAuthMixin:

    async def authenticate_jwt(self, token: str):
        try:
            UntypedToken(token)

            decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = decoded_token.get('user_id')
            if not user_id:
                logger.warning("[WS] JWT missing user_id")
                return None

            user = await self.get_user_by_id_jwt(user_id)
            if user:
                logger.info("[WS] JWT auth success for user_id=%s", user_id)
            return user

        except (InvalidToken, TokenError, jwt.ExpiredSignatureError, jwt.DecodeError) as exc:
            logger.warning("[WS] JWT authentication failed: %s", exc)
            return None

    @database_sync_to_async
    def get_user_by_id_jwt(self, user_id):

        try:
            return Executive.objects.get(id=user_id)
        except Executive.DoesNotExist:
            try:
                return UserProfile.objects.get(id=user_id)
            except UserProfile.DoesNotExist:
                return None


# -------------------- Custom Token Auth Mixin --------------------
class CustomTokenAuthMixin:


    async def authenticate_token(self, token: str):
        try:
            token_obj = await self.get_token_by_refresh_token(token)
            if not token_obj:
                logger.warning("[WS] Custom executive token not found")
                return None

            if getattr(token_obj, "expires_at", None):
                if token_obj.expires_at < timezone.now():
                    logger.warning("[WS] Executive token expired at %s", token_obj.expires_at)
                    return None

            executive = token_obj.executive
            if executive:
                logger.info("[WS] Custom token auth success for executive id=%s", executive.id)
            return executive

        except Exception as exc:
            logger.error("[WS] Custom token authentication failed: %s", exc, exc_info=True)
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
            return Executive.objects.get(id=user_id)
        except Executive.DoesNotExist:
            try:
                return UserProfile.objects.get(id=user_id)
            except UserProfile.DoesNotExist:
                return None


# -------------------- ExecutivesConsumer --------------------
class ExecutivesConsumer(AsyncWebsocketConsumer, CustomTokenAuthMixin):

    async def connect(self):
        headers = dict(self.scope.get('headers', []))
        token = headers.get(b'x-executive-token', b'').decode()

        if not token:
            query_string = self.scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token = params.get('token', [None])[0]

        if not token:
            logger.warning("[WS] ExecutivesConsumer: connect rejected — no token presented")
            await self.close(code=4001)
            return

        authenticated_user = await self.authenticate_token(token)
        if not authenticated_user:
            await self.accept()
            await self.send(text_data=json.dumps({
                "type": "authentication_error",
                "error": "Authentication failed. Token invalid or expired.",
                "code": 4001
            }))
            await self.close(code=4001)
            return

        if not isinstance(authenticated_user, Executive):
            logger.warning("[WS] ExecutivesConsumer: connect rejected — token not linked to an Executive")
            await self.close(code=4003)
            return

        self.user = authenticated_user

        path_exec_id = self.scope['url_route']['kwargs'].get('executive_id')
        if path_exec_id and str(path_exec_id) != str(self.user.executive_id):
            logger.warning("[WS] ExecutivesConsumer: path executive_id mismatch; closing")
            await self.close(code=4003)
            return

        self.executive_id = str(self.user.executive_id)
        self.users_group_name = "users_online"
        # ✅ Group name format: executive_<executive_id_code> — MUST match group_send in views.py
        self.private_group_name = f"executive_{self.executive_id}"

        await self.accept()

        # Join both broadcast group and private group
        await self.channel_layer.group_add(self.users_group_name, self.channel_name)
        await self.channel_layer.group_add(self.private_group_name, self.channel_name)

        # Update in-memory and DB statuses
        EXECUTIVE_STATUS[self.executive_id] = "online"
        await self.update_executive_status("online")
        await self.broadcast_status()

        logger.info("[WS] Executive connected: %s (executive_id=%s, group=%s)",
                    self.user.name, self.executive_id, self.private_group_name)

    async def disconnect(self, close_code):
        if hasattr(self, "executive_id"):
            EXECUTIVE_STATUS[self.executive_id] = "offline"
            await self.update_executive_status("offline")
            await self.broadcast_status()

        if hasattr(self, "users_group_name"):
            await self.channel_layer.group_discard(self.users_group_name, self.channel_name)
        if hasattr(self, "private_group_name"):
            await self.channel_layer.group_discard(self.private_group_name, self.channel_name)

        logger.info("[WS] Executive disconnected: executive_id=%s (code=%s)",
                    getattr(self, 'executive_id', 'unknown'), close_code)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            # Exec status update
            if msg_type == "status_update":
                new_status = data.get("status")
                valid = ["online", "offline", "oncall"]
                if new_status not in valid:
                    await self.send(text_data=json.dumps({"error": f"Invalid status, valid: {valid}"}))
                    return

                EXECUTIVE_STATUS[self.executive_id] = new_status
                await self.update_executive_status(new_status)
                await self.broadcast_status()
                await self.send(text_data=json.dumps({
                    "type": "status_changed",
                    "executive_id": self.executive_id,
                    "status": new_status
                }))
                return

            # Exec response to a user-initiated call
            if msg_type == "executive_response":
                user_id = data.get("user_id")
                call_id = data.get("call_id")
                callee_id = data.get("callee_id")
                status = data.get("status")

                if not user_id or not status:
                    await self.send(text_data=json.dumps({
                        "error": "Missing 'user_id' or 'status' in executive_response."
                    }))
                    return

                # 🔥 IMPORTANT FIX:
                # Always send to Django user's primary key group
                user_group = f"user_{int(user_id)}"

                payload = {
                    "type": "executive_response",
                    "executive_id": self.executive_id,
                    "user_id": user_id,
                    "call_id": call_id,
                    "callee_id": callee_id,
                    "status": status
                }

                await self.channel_layer.group_send(user_group, payload)

                await self.send(text_data=json.dumps({
                    "type": "executive_response_sent",
                    "to_user": user_id,
                    "call_id": call_id,
                    "status": status
                }))
                return
            # Unknown type - ignore or inform client
            await self.send(text_data=json.dumps({"warning": "Unknown message type"}))

        except Exception as exc:
            logger.error("[WS] Error in ExecutivesConsumer.receive: %s", exc, exc_info=True)
            await self.send(text_data=json.dumps({"error": str(exc)}))

    @database_sync_to_async
    def update_executive_status(self, status: str):
        try:
            self.user.is_online = (status == "online")
            self.user.on_call = (status == "oncall")
            self.user.save(update_fields=['is_online', 'on_call'])
            logger.info("[WS] DB status updated for executive_id=%s: %s", self.user.executive_id, status)
        except Exception as exc:
            logger.error("[WS] Error updating executive DB status: %s", exc, exc_info=True)

    async def broadcast_status(self):
        executive_data = await self.get_executives_detailed_status()
        await self.channel_layer.group_send(
            self.users_group_name,
            {"type": "status_update", "data": executive_data}
        )

    @database_sync_to_async
    def get_executives_detailed_status(self):

        result = []
        for exec_id, status in EXECUTIVE_STATUS.items():
            try:
                exec_obj = Executive.objects.get(executive_id=exec_id)
                result.append({
                    "executive_id": exec_id,
                    "name": exec_obj.name,
                    "status": status,
                    "is_available": status in ["online", "oncall"]
                })
            except Executive.DoesNotExist:
                result.append({
                    "executive_id": exec_id,
                    "name": "Unknown Executive",
                    "status": status,
                    "is_available": False
                })
        return result

    async def status_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                "type": "executive_status_list",
                "data": event["data"]
            }))
        except Exception as exc:
            logger.error("[WS] Error sending status_update to executive client: %s", exc, exc_info=True)

    async def call_event(self, event):
        """Legacy handler kept for backward compatibility (UsersConsumer → ExecutivesConsumer path)."""
        try:
            data = event.get("data", {})
            await self.send(text_data=json.dumps({
                "type": "incoming_call",
                "data": data
            }))
        except Exception as exc:
            logger.error("[WS] Error in call_event handler: %s", exc, exc_info=True)

    async def user_event(self, event):
        """Forward user_event directly to executive client in flat JSON structure."""
        try:
            await self.send(text_data=json.dumps(event))
        except Exception as exc:
            logger.error("[WS] Error in user_event handler: %s", exc, exc_info=True)

    # ─────────────────────────────────────────────────────────────────────────
    # ✅ FIX: Handlers for events sent via channel_layer.group_send() from
    #         calls/views.py → CallInitiateView.send_incoming_call_notification
    # The method name MUST exactly match the "type" field in the group_send payload.
    # ─────────────────────────────────────────────────────────────────────────

    async def incoming_call(self, event):
        """Deliver incoming call notification to connected executive."""
        try:
            logger.info("[WS] Delivering incoming_call event to executive_id=%s, call_id=%s",
                        getattr(self, 'executive_id', 'unknown'), event.get('call_id'))
            await self.send(text_data=json.dumps({
                "type": "incoming_call",
                "call_id": event.get("call_id"),
                "channel_name": event.get("channel_name"),
                "caller_name": event.get("caller_name"),
                "caller_uid": event.get("caller_uid"),
                "executive_token": event.get("executive_token"),
                "callee_uid": event.get("callee_uid"),
                "timestamp": event.get("timestamp"),
                "coins_per_second": event.get("coins_per_second"),
                "amount_per_min": event.get("amount_per_min"),
            }))
        except Exception as exc:
            logger.error("[WS] Error delivering incoming_call to executive: %s", exc, exc_info=True)

    async def call_missed(self, event):
        """Notify executive that a call was missed (no answer within timeout)."""
        try:
            logger.info("[WS] Delivering call_missed event to executive_id=%s, call_id=%s",
                        getattr(self, 'executive_id', 'unknown'), event.get('call_id'))
            await self.send(text_data=json.dumps({
                "type": "call_missed",
                "call_id": event.get("call_id"),
            }))
        except Exception as exc:
            logger.error("[WS] Error delivering call_missed to executive: %s", exc, exc_info=True)

    async def call_ended(self, event):
        """Notify executive that a call has ended."""
        try:
            await self.send(text_data=json.dumps({
                "type": "call_ended",
                **{k: v for k, v in event.items() if k != 'type'},
            }))
        except Exception as exc:
            logger.error("[WS] Error delivering call_ended to executive: %s", exc, exc_info=True)


# -------------------- UsersConsumer --------------------
class UsersConsumer(AsyncWebsocketConsumer, JWTAuthMixin):


    async def connect(self):
        headers = dict(self.scope.get('headers', []))
        raw_auth = headers.get(b'authorization', b'').decode()
        token = raw_auth.replace('Bearer ', '') if raw_auth else None

        # fallback to query param
        if not token:
            query_string = self.scope.get('query_string', b'').decode()
            params = parse_qs(query_string)
            token = params.get('token', [None])[0]

        if not token:
            print("DEBUG: Connect rejected: no JWT token")
            await self.close(code=4001)
            return

        authenticated_user = await self.authenticate_jwt(token)
        if not authenticated_user:
            print("DEBUG: JWT auth failed for user connection")
            await self.close(code=4001)
            return

        self.user = authenticated_user
        self.group_name = "users_online"
        self.user_group_name = f"user_{getattr(self.user, 'id', None)}"

        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)

        executive_data = await self.get_executives_detailed_status()
        await self.send(text_data=json.dumps({
            "type": "executive_status_list",
            "data": executive_data,
            "user_info": {
                "user_id": getattr(self.user, 'user_id', None) or getattr(self.user, 'id', None),
                "name": getattr(self.user, 'name', 'Unknown'),
                "user_type": "executive" if isinstance(self.user, Executive) else "user"
            }
        }))

        logger.info("[WS] User connected: user_id=%s, group=%s",
                    getattr(self.user, 'id', 'unknown'), self.user_group_name)

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

        logger.info("[WS] User disconnected: user_id=%s (code=%s)",
                    getattr(self, 'user', None) and getattr(self.user, 'id', 'unknown'), close_code)

    async def receive(self, text_data):

        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            # User initiating a call to an executive
            if msg_type == "user_event":
                executive_id = data.get("executive_id")
                if not executive_id:
                    await self.send(text_data=json.dumps({"error": "Missing 'executive_id' in payload."}))
                    return

                payload = {
                    "type": "user_event",  # mapped to ExecutivesConsumer.user_event
                    "executive_id": executive_id,
                    "user_id": data.get("user_id", getattr(self.user, 'id', None)),
                    "call": data.get("call", False),
                    "status": data.get("status"),
                    "call_id": data.get("call_id", 0),
                    "from_user": getattr(self.user, "name", "Unknown User")
                }

                executive_group = f"executive_{executive_id}"
                await self.channel_layer.group_send(executive_group, payload)

                # Acknowledge to sender
                await self.send(text_data=json.dumps({
                    "type": "user_event_sent",
                    "to_executive": executive_id,
                    "call_id": data.get("call_id", 0),
                    "status": data.get("status")
                }))
                return

            # Unknown message types can be handled or ignored
            await self.send(text_data=json.dumps({"warning": "Unknown message type"}))

        except Exception as exc:
            logger.error("[WS] Error in UsersConsumer.receive: %s", exc, exc_info=True)
            await self.send(text_data=json.dumps({"error": str(exc)}))

    @database_sync_to_async
    def get_executives_detailed_status(self):

        result = []
        for exec_id, status in EXECUTIVE_STATUS.items():
            try:
                exec_obj = Executive.objects.get(executive_id=exec_id)
                result.append({
                    "executive_id": exec_id,
                    "name": exec_obj.name,
                    "status": status,
                    "is_available": status in ["online", "oncall"]
                })
            except Executive.DoesNotExist:
                result.append({
                    "executive_id": exec_id,
                    "name": "Unknown Executive",
                    "status": status,
                    "is_available": False
                })
        return result

    async def executive_response(self, event):
        try:
            await self.send(text_data=json.dumps(event))
        except Exception as exc:
            logger.error("[WS] Error sending executive_response to user: %s", exc, exc_info=True)

    async def status_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                "type": "executive_status_list",
                "data": event.get("data", [])
            }))
        except Exception as exc:
            logger.error("[WS] Error sending status_update to user: %s", exc, exc_info=True)

    async def incoming_call(self, event):
        """Forward incoming call notification to user (if they are also in a user group)."""
        try:
            await self.send(text_data=json.dumps({
                "type": "incoming_call",
                **{k: v for k, v in event.items() if k != 'type'},
            }))
        except Exception as exc:
            logger.error("[WS] Error delivering incoming_call to user: %s", exc, exc_info=True)

    async def call_missed(self, event):
        """Forward call_missed notification to user."""
        try:
            await self.send(text_data=json.dumps({
                "type": "call_missed",
                "call_id": event.get("call_id"),
            }))
        except Exception as exc:
            logger.error("[WS] Error delivering call_missed to user: %s", exc, exc_info=True)

    async def call_ended(self, event):
        """Forward call_ended notification to user."""
        try:
            await self.send(text_data=json.dumps({
                "type": "call_ended",
                **{k: v for k, v in event.items() if k != 'type'},
            }))
        except Exception as exc:
            logger.error("[WS] Error delivering call_ended to user: %s", exc, exc_info=True)
