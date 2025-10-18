from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message
import json

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from django.contrib.auth import get_user_model  # move here
        self.User = get_user_model()

        self.room_group_name = "chat_1"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        messages = await self.get_messages()
        for msg in messages:
            await self.send(text_data=json.dumps({
                "message": msg.content,
                "fullname": msg.user.email
            }))

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        import json
        if text_data:
            data = json.loads(text_data)
            message = data.get("message")
            email = data.get("email")

            if not message or not email:
                return

            user = await self.get_user(email)
            if user:
                await self.save_message(user, message)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message",
                        "message": message,
                        "fullname": email
                    }
                )

    async def chat_message(self, event):
        import json
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "fullname": event["fullname"]
        }))

    @database_sync_to_async
    def get_user(self, email):
        return self.User.objects.get(email=email)

    @database_sync_to_async
    def save_message(self, user, message):
        Message.objects.create(user=user, content=message)

    @database_sync_to_async
    def get_messages(self):
        return list(Message.objects.all().order_by("timestamp")[:50])
