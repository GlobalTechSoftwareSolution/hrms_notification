import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Single chat room
        self.room_group_name = "chat_1"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send previous messages on connect
        messages = await self.get_messages()
        for msg in messages:
            await self.send(text_data=json.dumps({
                "message": msg.content,
                "fullname": msg.user.email
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get("message")
        email = data.get("email")
        user = await self.get_user(email)

        # Save message
        await self.save_message(user, message)

        # Broadcast message
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "fullname": email
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "fullname": event["fullname"]
        }))

    @database_sync_to_async
    def get_user(self, email):
        return User.objects.get(email=email)

    @database_sync_to_async
    def save_message(self, user, message):
        Message.objects.create(user=user, content=message)

    @database_sync_to_async
    def get_messages(self):
        # only fetch messages for room 1
        return list(Message.objects.all().order_by("timestamp"))
