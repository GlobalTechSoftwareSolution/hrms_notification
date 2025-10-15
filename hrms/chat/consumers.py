import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom, Message
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"chat_{self.room_name}"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Create room if it doesn't exist
        await self.get_or_create_room(self.room_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message', '')
        username = data.get('username', 'Anonymous')
        image_url = data.get('image', None)

        user = await self.get_user(username)
        room = await self.get_or_create_room(self.room_name)

        # Save message to DB
        msg = await self.create_message(user, room, message, image_url)

        # Broadcast message
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': msg.content,
                'username': username,
                'image': image_url,
                'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_user(self, username):
        return User.objects.filter(username=username).first()

    @database_sync_to_async
    def get_or_create_room(self, name):
        return ChatRoom.objects.get_or_create(name=name)[0]

    @database_sync_to_async
    def create_message(self, user, room, message, image):
        return Message.objects.create(user=user, room=room, content=message, image=image)
