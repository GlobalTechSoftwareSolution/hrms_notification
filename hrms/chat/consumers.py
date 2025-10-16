import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from accounts.models import Employee  # adjust import if path is different
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    ROOM_GROUP_NAME = "chat_1"  # fixed room id

    async def connect(self):
        # Join fixed chat group
        await self.channel_layer.group_add(
            self.ROOM_GROUP_NAME,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.ROOM_GROUP_NAME,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get("message")
        email = data.get("email")

        fullname = await self.get_fullname_from_email(email)

        # Broadcast message to all clients
        await self.channel_layer.group_send(
            self.ROOM_GROUP_NAME,
            {
                "type": "chat_message",
                "message": message,
                "fullname": fullname or email,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "fullname": event["fullname"]
        }))

    @database_sync_to_async
    def get_fullname_from_email(self, email):
        try:
            emp = Employee.objects.get(email__email=email)
            return emp.fullname
        except Employee.DoesNotExist:
            return None
