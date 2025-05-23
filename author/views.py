from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, action, authentication_classes, permission_classes
from .models import Author, FollowRequest
from django.utils import timezone
from inbox.models import Notification 
from posts.models import Post  
from .serializers import AuthorSerializer, FollowRequestSerializer
from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404, JsonResponse, HttpResponse, HttpResponseNotFound
import jwt
from datetime import datetime, timedelta
from rest_framework.exceptions import AuthenticationFailed  
from .serializers import UserSettingsForm
from django.contrib import messages
from django.conf import settings
from .models import Author, Following
from inbox.models import Inbox
from posts.models import Like
from posts.serializers import LikeSerializer
import json
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
import base64
from PIL import Image
from io import BytesIO


from django.urls import reverse


def profile_view(request, author_id):
    '''
    View to display the public profile of an author
    This view fetches the author by either FQID or author_serial
    '''
    try:
        # Try to get author by FQID first
        author = Author.objects.filter(id=author_id).first()
        
        if not author and 'http' in author_id:
            # For remote authors, try to find by the full FQID
            try:
                author = Author.objects.get(id=author_id)
            except Author.DoesNotExist:
                try:
                    uuid_part = author_id.split('/')[-1]  # Get the last part of the URL
                    author = Author.objects.get(author_serial=uuid_part)
                except (Author.DoesNotExist, ValueError, IndexError):
                    raise Http404("Remote author not found")
        elif not author:
            # For local authors, try by author_serial
            try:
                clean_id = author_id.split('/')[0]  # Remove any trailing paths
                author = Author.objects.get(author_serial=clean_id)
                # Construct FQID for local author
                author_fqid = f"{request.build_absolute_uri('/').rstrip('/')}/api/authors/{author.author_serial}"
                # Redirect to FQID URL
                return redirect('author_profile', author_id=author_fqid)
            except (Author.DoesNotExist, ValueError):
                raise Http404("Local author not found")

    except Exception as e:
        raise Http404(f"Author not found: {str(e)}")

    # Check if this is a remote author
    is_remote = not author.host.startswith(request.build_absolute_uri('/').rstrip('/'))

    # For consistency, always use FQID in URLs
    if author.id != author_id:
        return redirect('author_profile', author_id=author.id)

    # Rest of your existing profile_view code...
    is_following = False
    is_friends = False
    
    followers_count = Following.objects.filter(
        author2=author, 
        status='accepted'
    ).count()
    
    following_count = Following.objects.filter(
        author1=author, 
        status='accepted'
    ).count()
    
    if request.user.is_authenticated and request.user != author:
        is_following = Following.objects.filter(
            author1=request.user, 
            author2=author,
            status='accepted'
        ).exists()
        
        is_friends = Following.are_friends(request.user, author)
    
    visibility_exclusions = ['DELETED']
    if request.user == author:
        pass
    elif not is_friends and not is_following:
        visibility_exclusions.extend(['FRIENDS', 'UNLISTED'])
    elif not is_friends:
        visibility_exclusions.append('FRIENDS')

    posts = Post.objects.filter(
        author=author
    ).exclude(
        visibility__in=visibility_exclusions
    ).order_by('-published')

    context = {
        'author': author,
        'posts': posts,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'is_friends': is_friends,
        'logged_in_user': request.user,
        'is_own_profile': request.user == author,
        'is_remote': is_remote
    }
    
    return render(request, 'author/author_feed.html', context)


def author_about(request, author_id):
    '''
    View to display the about page of an author
    This view fetches the author by either FQID or author_serial
    '''
    try:
        # Try to get author by FQID first
        author = Author.objects.filter(id=author_id).first()
        
        if not author and 'http' in author_id:
            # For remote authors, try to find by the full FQID
            try:
                author = Author.objects.get(id=author_id)
            except Author.DoesNotExist:
                try:
                    uuid_part = author_id.split('/')[-1]  # Get the last part of the URL
                    author = Author.objects.get(author_serial=uuid_part)
                except (Author.DoesNotExist, ValueError, IndexError):
                    raise Http404("Remote author not found")
        elif not author:
            # For local authors, try by author_serial
            try:
                clean_id = author_id.split('/')[0]  # Remove any trailing paths
                author = Author.objects.get(author_serial=clean_id)
                # Construct FQID for local author
                author_fqid = f"{request.build_absolute_uri('/').rstrip('/')}/api/authors/{author.author_serial}"
                # Redirect to FQID URL
                return redirect('author-about', author_id=author_fqid)
            except (Author.DoesNotExist, ValueError):
                raise Http404("Local author not found")

    except Exception as e:
        raise Http404(f"Author not found: {str(e)}")

    # Check if this is a remote author
    is_remote = not author.host.startswith(request.build_absolute_uri('/').rstrip('/'))

    # For consistency, always use FQID in URLs
    if author.id != author_id:
        return redirect('author-about', author_id=author.id)

    # Get follower and following counts
    followers_count = Following.objects.filter(
        author2=author, 
        status='accepted'
    ).count()
    
    following_count = Following.objects.filter(
        author1=author, 
        status='accepted'
    ).count()

    # Check if the logged-in user is following this author
    is_following = False
    is_friends = False
    if request.user.is_authenticated and request.user != author:
        is_following = Following.objects.filter(
            author1=request.user, 
            author2=author,
            status='accepted'
        ).exists()
        
        is_friends = Following.are_friends(request.user, author)

    context = {
        'author': author,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'is_friends': is_friends,
        'logged_in_user': request.user,
        'is_own_profile': request.user == author,
        'is_remote': is_remote
    }
    
    return render(request, 'author/author_about.html', context)

@api_view(['GET'])
def api_get_like(request, like_fqid):
    """
    Retrieve a single like by its fully qualified ID (LIKE_FQID).
    """
    try:
        # Fetch the Like instance using the LIKE_FQID
        like = Like.objects.get(id=like_fqid)
        
        # Serialize the Like object
        like_data = {
            'id': like.id,
            'username': like.username,
            'post_id': like.object.id,
            'author_id': like.author.author_serial,
            'published': like.published,
            'type': like.type,
        }

        return Response(like_data, status=status.HTTP_200_OK)
    except Like.DoesNotExist:
        return Response({"error": "Like not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_single_like(request, author_serial, like_serial):
    print("Requested Author Serial:", author_serial)
    print("Requested Like Serial:", like_serial)

    # Get the author based on the provided author_serial
    author = get_object_or_404(Author, author_serial=author_serial)

    # Get the specific like by LIKE_SERIAL and ensure it belongs to the author
    like = get_object_or_404(Like, id=like_serial, author=author)

    # Serialize the like object
    like_serializer = LikeSerializer(like)

    # Return the serialized data
    return Response(like_serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_likes_by_author(request, author_serial):
    print("Requested Author Serial:", author_serial)

    # Get the author based on the provided author_serial
    author = get_object_or_404(Author, author_serial=author_serial)

    # Retrieve all likes by the author
    likes = Like.objects.filter(author=author)

    # Create a dictionary to store the latest likes per post
    latest_likes_dict = {}

    for like in likes:
        post_id = like.object.id
        if post_id not in latest_likes_dict:
            latest_likes_dict[post_id] = like
        else:
            # Compare published dates to find the latest like
            if like.published > latest_likes_dict[post_id].published:
                latest_likes_dict[post_id] = like

    # Get the latest likes as a list
    latest_likes = list(latest_likes_dict.values())

    # Serialize the latest likes queryset
    like_serializer = LikeSerializer(latest_likes, many=True)

    # Return the serialized data
    return Response(like_serializer.data, status=status.HTTP_200_OK)


def follow_author(request, object_author_serial):
    '''
    This view is used to follow the target author. It fetches the currently logged-in user and the target author.
    It then follows the target author using the follow method in the model.
    '''
    """Follow the target author."""
    if request.method == 'POST' and request.user.is_authenticated:
        actor = request.user  # The currently logged-in user
        target_author = get_object_or_404(Author, author_serial=object_author_serial)  # The author to be followed

        # Prevent users from following themselves
        if target_author != actor:
            # Follow the target author using the follow method in the model
            Following.follow(actor, target_author)
        
        # Optionally, check if they are now mutual followers (friends)
        if Following.are_friends(actor, target_author):
            message = f"You are now friends with {target_author.displayName}."
        
        # Redirect back to the referring page
        return redirect(request.META.get('HTTP_REFERER', '/'))

    return redirect('home_page')


def unfollow_author(request, object_author_serial):
    '''
    This view is used to unfollow the target author. It fetches the currently logged-in user and the target author.
    It then unfollows the target author using the unfollow method in the model.
    '''
    """Unfollow the target author."""
    if request.method == 'POST' and request.user.is_authenticated:
        actor = request.user  # The currently logged-in user
        target_author = get_object_or_404(Author, author_serial=object_author_serial)  # The author to be unfollowed

        # Prevent users from unfollowing themselves
        if target_author != actor:
            # Unfollow the target author using the unfollow method in the model
            Following.unfollow(actor, target_author)

        # Redirect back to the referring page
        return redirect(request.META.get('HTTP_REFERER', '/'))

    return redirect('home_page')

def following_list(request, author_id):
    '''
    View to display the list of authors that this author is following
    '''
    try:
        # Try to get author by FQID first
        author = Author.objects.filter(id=author_id).first()
        
        if not author and 'http' in author_id:
            # For remote authors, try to find by the full FQID
            try:
                author = Author.objects.get(id=author_id)
            except Author.DoesNotExist:
                try:
                    uuid_part = author_id.split('/')[-1]  # Get the last part of the URL
                    author = Author.objects.get(author_serial=uuid_part)
                except (Author.DoesNotExist, ValueError, IndexError):
                    raise Http404("Remote author not found")
        elif not author:
            # For local authors, try by author_serial
            try:
                clean_id = author_id.split('/')[0]  # Remove any trailing paths
                author = Author.objects.get(author_serial=clean_id)
                # Construct FQID for local author
                author_fqid = f"{request.build_absolute_uri('/').rstrip('/')}/api/authors/{author.author_serial}"
                # Redirect to FQID URL
                return redirect('following_list', author_id=author_fqid)
            except (Author.DoesNotExist, ValueError):
                raise Http404("Local author not found")

        # Get the list of authors being followed
        following_list = Following.objects.filter(
            author1=author,
            status='accepted'
        )

        context = {
            'author': author,
            'following_list': following_list,
            'followers_count': Following.objects.filter(author2=author, status='accepted').count(),
            'following_count': following_list.count(),
            'is_own_profile': request.user == author
        }
        
        return render(request, 'author/following_list.html', context)
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"Error in following list: {str(e)}")
        print(traceback.format_exc())
        raise Http404(f"Error finding following: {str(e)}")

def followers_list(request, author_id):
    '''
    View to display the list of followers for an author
    '''
    try:
        # Try to get author by FQID first
        author = Author.objects.filter(id=author_id).first()
        
        if not author and 'http' in author_id:
            # For remote authors, try to find by the full FQID
            try:
                author = Author.objects.get(id=author_id)
            except Author.DoesNotExist:
                try:
                    uuid_part = author_id.split('/')[-1]  # Get the last part of the URL
                    author = Author.objects.get(author_serial=uuid_part)
                except (Author.DoesNotExist, ValueError, IndexError):
                    raise Http404("Remote author not found")
        elif not author:
            # For local authors, try by author_serial
            try:
                clean_id = author_id.split('/')[0]  # Remove any trailing paths
                author = Author.objects.get(author_serial=clean_id)
                # Construct FQID for local author
                author_fqid = f"{request.build_absolute_uri('/').rstrip('/')}/api/authors/{author.author_serial}"
                # Redirect to FQID URL
                return redirect('followers_list', author_id=author_fqid)
            except (Author.DoesNotExist, ValueError):
                raise Http404("Local author not found")

        # Get the list of followers
        followers_list = Following.objects.filter(
            author2=author,
            status='accepted'
        )

        context = {
            'author': author,
            'followers_list': followers_list,
            'followers_count': followers_list.count(),
            'following_count': Following.objects.filter(author1=author, status='accepted').count(),
            'is_own_profile': request.user == author
        }
        
        return render(request, 'author/followers_list.html', context)
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"Error in followers list: {str(e)}")
        print(traceback.format_exc())
        raise Http404(f"Error finding followers: {str(e)}")


@api_view(['GET','DELETE','PUT'])
def manage_follower(request, author_serial, foreign_author_id):
    author = get_object_or_404(Author, author_serial=author_serial)

    from urllib.parse import unquote
    foreign_author_id = unquote(foreign_author_id)

    try:
        foreign_author = Author.objects.get(id=foreign_author_id)
    except Author.DoesNotExist:
        return Response({"detail": "Foreign author not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Handle GET request: Check if foreign author is following the author
    if request.method =='GET':
        is_follower = Following.is_following(foreign_author, author)
        if is_follower:
            follower_data = {
                "type": "author",
                "id": foreign_author_id,
                "host": foreign_author.host,
                "displayName": foreign_author.displayName,
                "page": f"{foreign_author.host}/authors/{foreign_author.author_serial}",
                "github": foreign_author.github,
                "profileImage": foreign_author.profileImage
            }
            return Response(follower_data, status=status.HTTP_200_OK)
        
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Handle DELETE request: Remove the follower relationship
    elif request.method =='DELETE':
        if Following.is_following(foreign_author, author):
            Following.unfollow(foreign_author, author)
            return Response({"detail": "Follower removed"}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "No follower relationship exists"}, status=status.HTTP_404_NOT_FOUND)
    
    # Handle PUT request: Add a follower relationship
    elif request.method =='PUT':
        new_following = Following.follow(foreign_author, author)
        if new_following:
            follower_data = {
                "type": "author",
                "id": foreign_author_id,
                "host": foreign_author.host,
                "displayName": foreign_author.displayName,
                "page": f"{foreign_author.host}/authors/{foreign_author.author_serial}",
                "github": foreign_author.github,
                "profileImage": foreign_author.profileImage,
                "message": f"New follower created for author {author.displayName}"
            }
            return Response(follower_data, status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "Already following"}, status=status.HTTP_200_OK)



@api_view(['GET'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
def api_list_authors(request):
    """
    GET: List all authors
    With pagination: GET ://service/api/authors?page=10&size=5
    Without pagination: GET ://service/api/authors
    """
    # Check authentication
    if not request.user.is_authenticated:
        return Response(
            {"error": "Authentication required"}, 
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Get pagination parameters from query string
    page = request.query_params.get('page')
    size = request.query_params.get('size')
    
    # Get all authors (excluding system accounts)
    authors = Author.objects.filter(isNode=False, is_superuser=False).order_by('displayName')
    
    # If both page and size are specified, apply pagination
    if page is not None and size is not None:
        try:
            page = int(page)
            size = int(size)
            # Calculate pagination
            start_index = (page - 1) * size
            end_index = start_index + size
            # Slice the queryset
            authors = authors[start_index:end_index]
        except ValueError:
            return Response(
                {"error": "Invalid page or size parameter"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Format authors using the helper function
    formatted_authors = [get_author_data(author) for author in authors]

    # Return response in specified format
    response_data = {
        "type": "authors",
        "authors": formatted_authors
    }

    return Response(response_data, status=status.HTTP_200_OK)

    
    
@api_view(['POST'])
def api_add_author(request):
    # Deserialize the incoming request data using the AuthorSerializer
    serializer = AuthorSerializer(data=request.data)

    # Validate and save the data if it's valid
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Author created successfully", "author": serializer.data}, status=status.HTTP_201_CREATED)

    # If data is invalid, return the errors
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET', 'PUT'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
def api_author_detail(request, author_serial=None):
    """
    URL: ://service/api/authors/{AUTHOR_SERIAL}/
    GET [local, remote]: retrieve AUTHOR_SERIAL's profile
    PUT [local]: update AUTHOR_SERIAL's profile
    """
    try:
        # Get author by serial
        author = get_object_or_404(Author, author_serial=author_serial)

        if request.method == 'GET':
            if not request.user.is_authenticated:
                return Response(
                    {"error": "Authentication required"}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )
            return Response(get_author_data(author), status=status.HTTP_200_OK)

        elif request.method == 'PUT':
            # Check if user is authenticated and is modifying their own profile
            if not request.user.is_authenticated or isinstance(request.auth, BasicAuthentication):
                return Response(
                    {"error": "Only local users can modify profiles"}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check if user is modifying their own profile
            if str(request.user.author_serial) != str(author_serial):
                return Response(
                    {"error": "You can only modify your own profile"}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            try:
                data = json.loads(request.body)
                
                # Update allowed fields
                author.displayName = data.get('displayName', author.displayName)
                author.github = data.get('github', author.github)
                author.page = data.get('page', author.page)

                if 'profileImage' in data:
                    author.profileImage = data['profileImage']

                author.save()

                return Response(get_author_data(author), status=status.HTTP_200_OK)

            except json.JSONDecodeError:
                return Response(
                    {'error': 'Invalid JSON data'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        
def get_author_data(author):
    """
    Helper function to format author data according to the API specification
    """
    # Normalize host first
    host = author.host.rstrip('/')
    if host.endswith('/api'):
        host = host[:-4]
    elif host.endswith('/api/'):
        host = host[:-5]
    
    # Add /api/ to normalized host
    api_host = f"{host}/api"
    
    profile_image = author.profileImage

    # Construct the author ID
    author_id = f"{api_host}/authors/{author.author_serial}"

    # Build the author data dictionary
    author_data = {
        "type": "author",
        "id": author_id,  # This should be the full author ID, not just the host
        "host": f"{host}/api/",  # Include trailing slash for consistency
        "displayName": author.displayName,
        "github": author.github,
        "profileImage": profile_image,
        "page": author.page,
        "url": author_id  # Adding url field as it's often required
    }

    return author_data


class AuthorPagination(PageNumberPagination):
    page_size = 100 # Default number of items per page
    page_size_query_param = 'size' # Custom query parameter for page size
    max_page_size = 1000 # Maximum number of items per page

    def get_paginated_response(self, data):
        # Customize the response format to only include `type` and `authors`
        return Response({
            "type": "authors",
            "authors": data
        })

class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    pagination_class = AuthorPagination

    @action(detail=False, methods=['POST'], url_path='send-follow-request')
    def send_follow_request(self, request):
        # Step 1: Get the author UUID from the request data
        actor_author_uuid = request.data.get('actor_uuid')
        target_author_uuid = request.data.get('author_uuid')

        # Step 2: Validate the presence of both UUIDs
        if not actor_author_uuid or not target_author_uuid:
            return Response({"detail": "Missing author UUIDs."}, status=status.HTTP_400_BAD_REQUEST)

        # Step 3: Fetch the authors by UUID
        try:
            actor_author = Author.objects.get(author_serial=actor_author_uuid)
            object_author = Author.objects.get(author_serial=target_author_uuid)
        except Author.DoesNotExist:
            return Response({"detail": "One or both authors not found."}, status=status.HTTP_404_NOT_FOUND)

        # Step 4: Check if a follow request already exists
        if FollowRequest.objects.filter(actor=actor_author, object_author=object_author).exists():
            return Response({"detail": "Follow request already sent."}, status=status.HTTP_400_BAD_REQUEST)

        # Step 5: Create a new follow request
        follow_request = FollowRequest(
            actor=actor_author,
            object_author=object_author,
            summary=f"{actor_author.displayName} wants to follow {object_author.displayName}",
            status='pending'  # Initial status set to 'pending'
        )
        
        follow_request.save()
        """

        # Step 6: Create a notification for the target author
        notification = Notification(
            author=object_author,
            type='follow',  # Set type to 'follow' for follow requests
            post=None,  # No post associated with this notification
            received_at=timezone.now()
        )
        notification.save()
        """
        


        # Step 6: Return the created follow request
        serializer = FollowRequestSerializer(follow_request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)



##########
''' Code for Author authentication/ Login to our website 
    https://www.youtube.com/watch?v=PUzgZrS_piQ
'''
def loginPage(request):
    return render(request, 'author/login.html')


@api_view(['POST'])
def login(request):
    # Check if 'displayName' and 'password' are in the request data
    display_name = request.data.get('displayName')
    password = request.data.get('password')

    if not display_name:
        return Response({"detail": "Display name is required"}, status=status.HTTP_400_BAD_REQUEST)

    if not password:
        return Response({"detail": "Password field is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Get the Author object
    try:
        author = get_object_or_404(Author, displayName=display_name)
        print(f"Author found: {author}")
    except Author.DoesNotExist:
        return Response({"detail": "Author not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check if author is verified
    if not author.isVerified:
        return Response({"detail": "Not Verified by admin"}, status=status.HTTP_401_UNAUTHORIZED)

    # Check if password matches
    if not author.check_password(password):
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # Log password check
    print(f"Password check for {display_name}: {author.check_password(password)}")

    # Generate the JWT token
    payload = {
        'id': author.displayName,
        'author_id': str(author.author_serial),
        'exp': timezone.now() + timedelta(days=1),  # Token expiration
        'iat': timezone.now()
    }

    # Log token creation
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    print(f"Generated JWT token: {token}")

    # Set the JWT token in a cookie
    response = Response({"detail": "Login successful"})
    response.set_cookie(
        key=settings.JWT_AUTH_COOKIE,
        value=token,
        httponly=True,
        secure=True,  # Ensure HTTPS is used in production
        samesite='Strict'  # Secure cookie behavior
    )

    return response
@api_view(['POST'])
def signup(request):
    # Validate and serialize the incoming request data
    serializer = AuthorSerializer(data=request.data, partial=True)

    # Check if serializer is valid
    if serializer.is_valid():
        # Save the new author instance to the database
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # Return error response if username exists or validation fails
    return Response({"detail": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_author_from_cookie(request):
    token = request.COOKIES.get('jwt')
    if not token:
        return AuthenticationFailed("Unauthenticated")
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return AuthenticationFailed("Unauthenticated")
    
    author = Author.objects.filter(displayName = payload['id']).first()
    serializer = AuthorSerializer(instance = author)
    return Response(serializer.data)

@api_view(['POST'])
def logout(request):
    response = Response()
    response.delete_cookie('jwt')
    response.data = {
        "message": "success"
    }
    return render(request, 'author/login.html')


def user_settings(request, author_id):
    try:
        # Clean the author_id by removing any trailing paths
        clean_author_id = author_id.split('/')[0] if '/' in author_id else author_id
        
        # Try to get author by FQID first
        author = Author.objects.filter(id=author_id).first()
        
        if not author and 'http' in author_id:
            # For remote authors, try to find by the full FQID
            try:
                author = Author.objects.get(id=author_id)
            except Author.DoesNotExist:
                try:
                    uuid_part = author_id.split('/')[-1]  # Get the last part of the URL
                    author = Author.objects.get(author_serial=uuid_part)
                except (Author.DoesNotExist, ValueError, IndexError):
                    raise Http404("Remote author not found")
        elif not author:
            # For local authors, try by author_serial
            try:
                author = Author.objects.get(author_serial=clean_author_id)
                # Construct FQID for local author
                author_fqid = f"{request.build_absolute_uri('/').rstrip('/')}/api/authors/{author.author_serial}"
                # Redirect to FQID URL if not already using it
                if author_fqid != author_id:
                    return redirect('user-settings', author_id=author_fqid)
            except (Author.DoesNotExist, ValueError):
                raise Http404("Local author not found")

        # Check if user has permission to access settings
        if request.user != author:
            raise Http404("You don't have permission to access these settings")

        if request.method == 'POST':
            form = UserSettingsForm(request.POST, request.FILES, instance=author)
            if form.is_valid():
                form.save()
                messages.success(request, 'Profile changes saved successfully!')
                return redirect('author_profile', author_id=author.id)  # Use FQID for redirect
        else:
            form = UserSettingsForm(instance=author)

        context = {
            'form': form,
            'author': author,
            'followers_count': Following.objects.filter(author2=author, status='accepted').count(),
            'following_count': Following.objects.filter(author1=author, status='accepted').count(),
            'redirect_url': request.build_absolute_uri(
                reverse('author_profile', kwargs={'author_id': author.id})  # Use FQID for URL
            )
        }
        
        return render(request, 'author/user_settings.html', context)
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"Error in user settings: {str(e)}")
        print(traceback.format_exc())
        raise Http404(f"Error in user settings: {str(e)}")

def serve_profile_image(request, author_serial):
    author = get_object_or_404(Author, author_serial=author_serial)
    
    if author.profileImage:
        image_data = base64.b64decode(author.profileImage)
        image_stream = BytesIO(image_data)

        # Open the image using Pillow to determine its format
        try:
            with Image.open(image_stream) as img:
                image_type = img.format.lower()  # Get image format and convert to lowercase
        except IOError:
            return HttpResponse(image_data, content_type="application/octet-stream")
        
        if not image_type:
            return HttpResponse(image_data, content_type="application/octet-stream")
        
        return HttpResponse(image_data, content_type=f"image/{image_type}")
    else:
        return HttpResponse(status=404)


from django.core.files.storage import default_storage
from django.views.decorators.csrf import csrf_exempt
@csrf_exempt
def upload_profile_image(request):
    if request.method == 'POST' and request.FILES.get('file'):
        image = request.FILES['file']
        path = default_storage.save(f"profile_images/{image.name}", image)
        image_url = f"{request.scheme}://{request.get_host()}/media/{path}"
        return JsonResponse({'url': image_url})
    return JsonResponse({'error': 'Invalid request'}, status=400)