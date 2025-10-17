from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages

def login_view(request):
    """
    Login view for chat.
    """
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return redirect("chat_room")  # redirect to chat room
        else:
            messages.error(request, "Invalid email or password")

    return render(request, "chat/login.html")


def chat_room(request):
    """
    Chat room page.
    """
    if not request.user.is_authenticated:
        return redirect("chat_login")  # redirect to login if not logged in

    return render(request, "chat/chat_room.html", {"user_email": request.user.email})
