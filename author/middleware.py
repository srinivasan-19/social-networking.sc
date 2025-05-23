from django.utils.deprecation import MiddlewareMixin
import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model

User = get_user_model()

class JWTAuthenticationMiddleware(MiddlewareMixin):
    '''
    Middleware to authenticate users using JWT token
    '''
    def process_request(self, request):
        # Exclude the admin URL path from JWT authentication
        if request.path.startswith('/admin/'):
            return  # Bypass JWT authentication for admin

        # Get the JWT token from cookies
        token = request.COOKIES.get('jwt')  
        if token:
            try:
                # Decode the JWT token using the secret key
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])

                # Get the user from the decoded JWT payload
                user = User.objects.get(author_serial=payload['author_id'])

                # Attach the user and jwt payload to request
                request.user = user
                request.jwt_payload = payload  # Now attach the JWT payload
            except (jwt.ExpiredSignatureError, jwt.DecodeError, User.DoesNotExist):
                # If token is invalid or user does not exist, set as AnonymousUser
                request.user = AnonymousUser()
                request.jwt_payload = None  # No valid payload
        else:
            # No JWT token, set the user as AnonymousUser
            request.user = AnonymousUser()
            request.jwt_payload = None  # No payload
