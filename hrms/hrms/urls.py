"""
URL configuration for hrms project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import path, include
from accounts.views import health_check
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import recognize_face

def root_redirect(request):
    return HttpResponseRedirect('/api/accounts/login/')  # or any other route

def home(request):
    return HttpResponse("Welcome to HRMS backend! Use /api/accounts/ for endpoints.")

urlpatterns = [
    path('', home, name='home'),  # Or use root_redirect
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path("health/", health_check, name="health"),
    path("recognize_face/", recognize_face, name="recognize_face"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)