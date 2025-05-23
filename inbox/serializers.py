from rest_framework import serializers
from .models import Notification
from posts.models import Post, Comment, Like
from author.models import Author

class NotificationSerializer(serializers.ModelSerializer):
    author = serializers.CharField()
    post = serializers.PrimaryKeyRelatedField(queryset=Post.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Notification
        fields = ['id', 'author', 'type', 'post', 'received_at']
