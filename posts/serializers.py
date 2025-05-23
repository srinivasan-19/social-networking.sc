from rest_framework import serializers
from .models import Post, Comment, Like
from author.serializers import AuthorSerializer

class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    class Meta:
        model = Comment
        # specifies which fields to serialize
        fields = ['type', 'author', 'username', 'comment', 'contentType', 'published', 'id', 'uuid', 'post']
class LikeSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    class Meta:
        model = Like
        # specifies which fields to serialize
        fields = ['type', 'object', 'published','author','id']

class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True) # So the response actually return the author object instead of just id
    comments = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()
    class Meta:
        model = Post
        fields = ['id','uuid','type','page', 'title', 'description', 'contentType', 'content', 'visibility', 'author', 'published', 'comments', 'likes']
    
    def get_comments(self, obj):
        comments_queryset = obj.comments.all().order_by('-published')[:5] 
        return {
            "type": "comments",
            "page": f"{obj.id}",
            "id": f"{obj.id}/comments",
            "page_number": 1,
            "size": 5,
            "count": obj.comments.count(),
            "src": CommentSerializer(comments_queryset, many=True).data,
        }

    def get_likes(self, obj):
        likes_queryset = obj.likes.all().order_by('-published')[:5] 
        return {
            "type": "likes",
            "page": f"{obj.id}",
            "id": f"{obj.id}/likes",
            "page_number": 1,
            "size": 5,
            "count": obj.likes.count(),
            "src": LikeSerializer(likes_queryset, many=True).data,
        }

    def validate_title(self, value):
        if not value:
            raise serializers.ValidationError("Title cannot be empty.")
        if len(value) < 1 or len(value) > 200:
            raise serializers.ValidationError("Title must be between 1 and 200 characters.")
        return value

    def validate_description(self, value):
        if len(value) > 500:
            raise serializers.ValidationError("Description cannot exceed 500 characters.")
        return value

    def create(self, validated_data):
        # Remove author from validated_data as it should be set from the view
        # author = validated_data.pop('author', None)
        post = Post.objects.create(**validated_data)
        return post

    def update(self, instance, validated_data):
        # Update instance with the validated data
        instance.title = validated_data.get('title', instance.title)
        instance.description = validated_data.get('description', instance.description)
        instance.contentType = validated_data.get('contentType', instance.contentType)
        instance.content = validated_data.get('content', instance.content)
        instance.visibility = validated_data.get('visibility', instance.visibility)
        instance.save()
        return instance