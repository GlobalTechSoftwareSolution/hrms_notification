from django.db import models
from django.conf import settings  # <- safe reference

class Message(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # safe for custom user model
        on_delete=models.CASCADE,
        related_name="messages"
    )
    content = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user}: {self.content or 'Message'}"
