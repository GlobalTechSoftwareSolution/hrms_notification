from django.shortcuts import render
from .models import ChatRoom

def room(request, room_name):
    room, created = ChatRoom.objects.get_or_create(name=room_name)
    messages = room.messages.order_by('timestamp')
    return render(request, 'chat/room.html', {'room_name': room_name, 'messages': messages})
