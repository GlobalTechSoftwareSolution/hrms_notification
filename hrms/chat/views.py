from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from .models import Message, VideoRoom
from .serializers import MessageSerializer
from django.http import JsonResponse
import random

# Login page for chat
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, email=email, password=password)
        if user:
            login(request, user)
            return redirect('chat_room')
    return render(request, 'chat/login.html')

def chat_room(request):
    return render(request, 'chat/chat_room.html')

def create_video_room(request):
    if request.method == "POST":
        code = str(random.randint(1000, 9999))
        VideoRoom.objects.create(code=code, created_by=request.user)
        return redirect('chat_room')
    return render(request, 'chat/create_video_room.html')


@login_required
def join_video_room(request):
    if request.method == "POST":
        code = request.POST.get('code')
        try:
            room = VideoRoom.objects.get(code=code)
            return JsonResponse({'success': True, 'code': room.code})
        except VideoRoom.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid Room Code'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})
