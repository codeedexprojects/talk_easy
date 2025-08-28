# app_name/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print("WebSocket Connected ✅")

    async def disconnect(self, close_code):
        print("WebSocket Disconnected ❌")

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")

        if action == "call":
            await self.channel_layer.group_add("calls", self.channel_name)
            await self.channel_layer.group_send(
                "calls",
                {
                    "type": "call.message",
                    "message": data.get("message", "Incoming call"),
                }
            )

    async def call_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"]
        }))
