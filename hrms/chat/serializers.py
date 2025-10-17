from rest_framework import serializers
from .models import Message, VideoRoom

class MessageSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'user_email', 'content', 'timestamp']

class VideoRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoRoom
        fields = ['code', 'created_by', 'created_at']
