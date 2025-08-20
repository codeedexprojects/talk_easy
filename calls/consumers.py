import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .models import AgoraCallHistory
from executives.models import Executive


class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:   # ✅ fix anonymous check
            await self.close()
            return
        
        # Get user type from URL or user model
        self.user_type = self.scope['url_route']['kwargs'].get('user_type', 'client')
        self.user_id = str(self.user.id)
        
        # Create group names
        self.user_group_name = f"user_{self.user_type}_{self.user_id}"
        
        # Join user group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "user_id": self.user_id,
            "user_type": self.user_type
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "user_group_name"):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")
            
            if message_type == "call_response":
                await self.handle_call_response(text_data_json)
            elif message_type == "heartbeat":
                await self.send(text_data=json.dumps({"type": "heartbeat_ack"}))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Invalid JSON format"
            }))

    async def handle_call_response(self, data):
        """Handle executive's response to incoming call"""
        call_id = data.get("call_id")
        response = data.get("response")  # 'accept' or 'reject'
        callee_uid = data.get("callee_uid")
        
        if not call_id or not response:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "call_id and response are required"
            }))
            return
            
        call = await self.get_call_by_id(call_id)
        if not call:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Call not found"
            }))
            return
            
        if response == "accept":
            if not callee_uid:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "callee_uid is required for accepting calls"
                }))
                return
                
            updated_call = await self.accept_call(call_id, callee_uid)
            
            # ✅ Notify caller group
            caller_group = f"user_client_{call.user_id}"
            await self.channel_layer.group_send(
                caller_group,
                {
                    "type": "call_accepted",
                    "call_id": call_id,
                    "channel_name": call.channel_name,
                    "executive_token": updated_call["executive_token"],
                    "callee_uid": callee_uid
                }
            )
            
        elif response == "reject":
            await self.reject_call(call_id)
            
            caller_group = f"user_client_{call.user_id}"
            await self.channel_layer.group_send(
                caller_group,
                {
                    "type": "call_rejected",
                    "call_id": call_id,
                    "message": "Executive rejected the call"
                }
            )

    # --- WebSocket event handlers ---
    async def incoming_call(self, event):
        await self.send(text_data=json.dumps({
            "type": "incoming_call",
            "call_id": event["call_id"],
            "channel_name": event["channel_name"],
            "caller_name": event.get("caller_name", "Unknown"),
            "caller_uid": event["caller_uid"],
            "timestamp": event["timestamp"]
        }))

    async def call_accepted(self, event):
        await self.send(text_data=json.dumps({
            "type": "call_accepted",
            "call_id": event["call_id"],
            "channel_name": event["channel_name"],
            "executive_token": event["executive_token"],
            "callee_uid": event["callee_uid"]
        }))

    async def call_rejected(self, event):
        await self.send(text_data=json.dumps({
            "type": "call_rejected",
            "call_id": event["call_id"],
            "message": event["message"]
        }))

    async def call_ended(self, event):
        await self.send(text_data=json.dumps({
            "type": "call_ended",
            "call_id": event["call_id"],
            "reason": event.get("reason", "Call ended"),
            "ended_by": event.get("ended_by", "unknown")
        }))

    async def call_missed(self, event):
        await self.send(text_data=json.dumps({
            "type": "call_missed",
            "call_id": event["call_id"],
            "message": "Call was missed"
        }))

    # --- Database operations ---
    @database_sync_to_async
    def get_call_by_id(self, call_id):
        try:
            return AgoraCallHistory.objects.get(id=call_id, is_active=True)
        except AgoraCallHistory.DoesNotExist:
            return None

    @database_sync_to_async
    def accept_call(self, call_id, callee_uid):
        from calls.utils import generate_agora_token
        from django.utils import timezone
        
        call = AgoraCallHistory.objects.get(id=call_id)
        executive_token = generate_agora_token(call.channel_name, callee_uid)
        
        call.callee_uid = callee_uid
        call.executive_token = executive_token
        call.status = "joined"
        call.joined_at = timezone.now()
        call.save()
        
        return {
            "executive_token": executive_token,
            "callee_uid": callee_uid
        }

    @database_sync_to_async
    def reject_call(self, call_id):
        from django.utils import timezone
        
        call = AgoraCallHistory.objects.get(id=call_id)
        call.status = "rejected"
        call.is_active = False
        call.end_time = timezone.now()
        call.save()
        
        # Free up executive
        call.executive.on_call = False
        call.executive.save(update_fields=["on_call"])
