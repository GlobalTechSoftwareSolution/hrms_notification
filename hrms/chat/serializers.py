from rest_framework import serializers
from .models import Message

class MessageSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'user_email', 'content', 'timestamp']
