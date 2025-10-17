from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="chat_login"),
    path("chat/", views.chat_room, name="chat_room"),
]
