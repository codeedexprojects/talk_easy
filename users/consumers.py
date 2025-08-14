# executives/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from executives.models import Executive
from executives.serializers import ExecutiveSerializer


class ExecutiveConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("executives_group", self.channel_name)
        await self.accept()
        await self.send_executive_list()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("executives_group", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('action') == 'get_executives':
            await self.send_executive_list()

    async def send_executive_list(self):
        executives_data = await self.get_executives_data()
        await self.send(text_data=json.dumps(executives_data))

    async def broadcast_executive_list(self, event):
        await self.send_executive_list()

    @database_sync_to_async
    def get_executives_data(self):
        executives = Executive.objects.all().order_by('-created_at')
        serializer = ExecutiveSerializer(executives, many=True)
        return serializer.data
