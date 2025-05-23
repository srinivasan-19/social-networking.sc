from rest_framework.authentication import BaseAuthentication
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
import jwt

User = get_user_model()

class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.COOKIES.get('jwt')
        if not token:
            return None  # No token, so return None (anonymous user)
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user = User.objects.get(author_serial=payload['author_id'])
            return (user, None)  # Return user and None for auth
        except (jwt.ExpiredSignatureError, jwt.DecodeError, User.DoesNotExist):
            return None  # Invalid token or user does not exist

