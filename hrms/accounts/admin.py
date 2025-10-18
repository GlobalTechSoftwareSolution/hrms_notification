from django.contrib import admin
from django.apps import apps
from .models import Holiday

# Get all models from the current app
app = apps.get_app_config('accounts')

for model_name, model in app.models.items():
    if model != Holiday:  # Skip Holiday to avoid double registration
        try:
            admin.site.register(model)
        except admin.sites.AlreadyRegistered:
            pass  # Skip if already registered

# Register Holiday with a custom admin
@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "type", "country")
    list_filter = ("year", "month", "type", "country")
    search_fields = ("name",)
