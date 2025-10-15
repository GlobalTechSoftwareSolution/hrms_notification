# chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from accounts.models import Employee  # adjust import path if different

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"chat_{self.room_name}"

        # Join chat group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave chat group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """
        Handle received message from WebSocket and broadcast to the room.
        """
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message")
        email = text_data_json.get("email")  # Sender's email passed from frontend

        # Get fullname from Employee table
        fullname = await self.get_fullname_from_email(email)

        # Broadcast message to the group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "fullname": fullname or email,  # fallback to email if not found
            }
        )

    async def chat_message(self, event):
        """
        Send message to WebSocket.
        """
        message = event["message"]
        fullname = event["fullname"]

        await self.send(text_data=json.dumps({
            "message": message,
            "fullname": fullname
        }))

    @database_sync_to_async
    def get_fullname_from_email(self, email):
        """
        Fetch the employee's fullname from DB based on email.
        """
        try:
            emp = Employee.objects.get(email__email=email)
            return emp.fullname
        except Employee.DoesNotExist:
            return None
