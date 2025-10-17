import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Single room for now
        self.room_group_name = "chat_1"
        
        # Check if channel layer is available
        if self.channel_layer is None:
            print("Error: Channel layer is not configured or unavailable")
            await self.close()
            return
            
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send previous messages
        messages = await self.get_messages()
        for msg in messages:
            await self.send(text_data=json.dumps({
                "message": msg.content,
                "fullname": msg.user.email
            }))

    async def disconnect(self, code):
        if self.channel_layer is not None:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                message = data.get("message")
                email = data.get("email")
                
                if not message or not email:
                    return
                    
                user = await self.get_user(email)
                if user:
                    await self.save_message(user, message)
                    
                    # Check if channel layer is available before sending group message
                    if self.channel_layer is not None:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                "type": "chat_message",
                                "message": message,
                                "fullname": email
                            }
                        )
                    else:
                        print("Warning: Channel layer is not available for group send")
        except Exception as e:
            print(f"Error in receive: {e}")

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "fullname": event["fullname"]
        }))

    @database_sync_to_async
    def get_user(self, email):
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def save_message(self, user, message):
        Message.objects.create(user=user, content=message)  # type: ignore

    @database_sync_to_async
    def get_messages(self):
        return list(Message.objects.all().order_by("timestamp")[:50])  # type: ignore