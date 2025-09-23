import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

# Global dictionary for executive statuses
EXECUTIVE_STATUS = {}

class ExecutivesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
       
        # Check authentication
        if not user or isinstance(user, AnonymousUser):
            await self.close(code=4001)
            return
       
        # Get executive ID from URL path or use user ID as default
        path_executive_id = self.scope['url_route']['kwargs'].get('executive_id')
        self.executive_id = str(path_executive_id) if path_executive_id else str(user.id)
        self.users_group_name = "users_online"
       
        # Accept connection FIRST
        await self.accept()
        
        # Then do other operations
        await self.channel_layer.group_add(self.users_group_name, self.channel_name)
        
        EXECUTIVE_STATUS[self.executive_id] = "offline"
        await self.broadcast_status()

    async def disconnect(self, close_code):
        if hasattr(self, "executive_id"):
            EXECUTIVE_STATUS[self.executive_id] = "offline"
            await self.broadcast_status()
           
        if hasattr(self, "users_group_name"):
            await self.channel_layer.group_discard(self.users_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            
            # Handle connect/disconnect messages
            if "connect" in data:
                if data["connect"]:
                    EXECUTIVE_STATUS[self.executive_id] = "online"
                else:
                    EXECUTIVE_STATUS[self.executive_id] = "offline"
                await self.broadcast_status()
                
            elif "oncall" in data:
                EXECUTIVE_STATUS[self.executive_id] = "oncall" if data["oncall"] else "online"
                await self.broadcast_status()
                
            # Send acknowledgment
            await self.send(text_data=json.dumps({
                "type": "ack",
                "executive_id": self.executive_id,
                "status": EXECUTIVE_STATUS[self.executive_id],
                "message": f"Status updated to {EXECUTIVE_STATUS[self.executive_id]}"
            }))
           
        except Exception as e:
            await self.send(text_data=json.dumps({"error": str(e)}))

    async def broadcast_status(self):
        try:
            await self.channel_layer.group_send(
                self.users_group_name,
                {
                    "type": "status_update",
                    "data": [
                        {"executive_id": exec_id, "status": status}
                        for exec_id, status in EXECUTIVE_STATUS.items()
                    ]
                }
            )
        except Exception:
            pass

    async def status_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                "type": "executive_status_list",
                "data": event["data"]
            }))
        except Exception:
            pass


class UsersConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "users_online"
        
        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        
        # Send current status
        await self.send(text_data=json.dumps({
            "type": "executive_status_list",
            "data": [
                {"executive_id": exec_id, "status": status}
                for exec_id, status in EXECUTIVE_STATUS.items()
            ]
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def status_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "executive_status_list",
            "data": event["data"]
        }))