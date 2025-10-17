from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('chat/', views.chat_room, name='chat_room'),
    path('create_video/', views.create_video_room, name='create_video_room'),
    path('video/join/', views.join_video_room, name='join_video_room'),
]
