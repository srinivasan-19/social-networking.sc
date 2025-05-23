from rest_framework import serializers
from .models import Author, FollowRequest
from django import forms

class AuthorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Author
        fields = ['type','id', 'host', 'displayName', 'github', 'profileImage', 'page', 'password']
        extra_kwargs = {'password': {'write_only': True}}
    
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = self.Meta.model(**validated_data)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance

    
    # def update(self, instance, validated_data):
    #     instance.choice_text = validated_data.get('choice_text', instance.choice_text)
    #     instance.question = validated_data.get('question', instance.question)
    #     instance.votes = validated_data.get('votes', instance.votes)
    #     instance.save()
    #     return instance



class FollowRequestSerializer(serializers.ModelSerializer):
    actor = AuthorSerializer(read_only=True)
    object_author = AuthorSerializer(read_only=True)

    class Meta:
        model = FollowRequest
        fields = ['actor', 'object_author', 'summary', 'status']
        depth = 1
class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ['displayName', 'github', 'profileImage']
        widgets = {
            'profileImage': forms.FileInput(),
        }