from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404, reverse, get_object_or_404
from .models import Post, Comment, Like, Author, githubPostIds, Following, Likes
import base64
import jwt
import markdown
from rest_framework.decorators import api_view, renderer_classes, authentication_classes, permission_classes
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from rest_framework import viewsets
from .serializers import PostSerializer, CommentSerializer, LikeSerializer
from author.views import get_author_from_cookie
from django.conf import settings
from django.contrib import messages
from urllib.parse import unquote
from requests.auth import HTTPBasicAuth
import requests
from django.utils import timezone
import logging
from inbox.models import Inbox


from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
# Create your views here.
def post(request):
    author_id = get_author_from_cookie(request).data.get('id')
    author = get_object_or_404(Author, id=author_id)
    return render(request, "posts/createPost.html", {'author': author})

class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer

# CommentViewSet to manage Comment API actions
class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer

# LikeViewSet to manage Like API actions
class LikeViewSet(viewsets.ModelViewSet):
    queryset = Like.objects.all()
    serializer_class = LikeSerializer


def send_comment_to_remote_nodes(payload, comment, user):
    """
    Send like notification to all relevant remote nodes.
    """
    recipients = set()

    # Determine the author of the liked object (post or comment)
    object_author = user

    if not object_author:
        logging.error("Object author not found")
        return

    # Get followers or other visibility-related recipients if needed
    followers = Following.get_followers(object_author)
    friends = Following.objects.filter(
        author2=object_author,
        status='accepted'
    ).select_related('author1')

    recipients.update([f.author1 for f in followers])
    recipients.update([f.author1 for f in friends])

    # Send to remote nodes
    nodes = Author.objects.filter(isNode=True)
    for recipient in recipients:
        for node in nodes:
            if object_author.host.endswith('/api/'):
                object_author.host = object_author.host.split('/api/')[0]

            if recipient.host == node.host and recipient.host != comment.author.host:
                try:
                    # Prepare headers for the request
                    headers = {
                        "Authorization": f"Basic {base64.b64encode(f'{node.displayName}:{node.first_name}'.encode()).decode()}",
                        "Content-Type": "application/json",
                        "host": node.host.split('//')[1],
                        "X-original-host": "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
                    }

                    recipient_uuid = recipient.id.split('/')[-1]
                    print("Sending like to recipient:", recipient_uuid)

                    # Send like payload to the recipient's inbox
                    response = requests.post(
                        f"{recipient.host}/api/authors/{recipient_uuid}/inbox",
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                except Exception as e:
                    logging.error(f"Failed to send like to {recipient.host}: {str(e)}")
                    if hasattr(e, 'response'):
                        logging.error(f"Response content: {e.response.content}")
                    continue
                
# API to create a comment
@api_view(['POST'])
def create_comment(request, post_uuid):
    post = get_object_or_404(Post, uuid=post_uuid)
    token = request.COOKIES.get('jwt')
    
    if not token:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        username = payload['id']  # Assuming 'id' is the username or display name
        user = Author.objects.get(displayName=username)
    except jwt.ExpiredSignatureError:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)

    # Process the comment data
    content = request.data.get('comment')
    if not content:
        return Response({"error": "Content is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    comment = Comment(username=username, comment=content, post=post, author=user, type='comment')
    host = request.get_host()
    comment._host = host  # Set the host as an attribute on the instance
    comment.save()

    # Serialize the created comment
    comment_serializer = CommentSerializer(comment)
    if hasattr(user, 'host') and not user.host.endswith('/api/'):
        user.host = user.host.rstrip('/') + '/api/'
    
    # Prepare the payload for remote comment
    payload = {
        "type": "comment",
        "author": {
                        "type": "author",
                        "id": user.id,
                        "host": user.host,
                        "displayName": user.displayName,
                        "page": user.page,
                        "github": user.github,
                        "profileImage": user.profileImage,
                    }, 
        "comment": comment.comment,
        "contentType": "text/markdown",
        "published": comment.published.isoformat(),
        "id": comment.id,
        "post": post.id,
        "likes": {
            "type": "likes",
            "page": f"{request.scheme}://{request.get_host()}/posts/{post.uuid}/likes/",
            "id": post.id,
            "size": 50,
            "count": 0,
            "src": []
        }
    }
    print("payload for sending local comment: ", payload)
    send_comment_to_remote_nodes(payload, comment, user)
    print("comments sent successfully")

    # Returning JSON for Ajax or redirect
    if request.accepts('application/json'):
        return Response(comment_serializer.data, status=status.HTTP_201_CREATED)
    else:
        #return redirect('viewPost', id=post.uuid)
        return redirect(request.META.get('HTTP_REFERER'))

@api_view(['GET'])
def get_comment(request, comment_id=None, author_serial=None, post_serial=None, remote_comment_FQID=None):
    print("in")
    print("comment_id: ", comment_id)

    # For authenticated users
    if request.user.is_authenticated:
        if comment_id:
            comment = get_object_or_404(Comment, uuid=comment_id)
            print("comment: ", comment)
            comment_serializer = CommentSerializer(comment)
        else:
            return Response({"error": "Invalid parameters"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        # For authenticated remote requests
        auth = BasicAuthentication()
        user, auth_status = auth.authenticate(request)

        if not user or not IsAuthenticated().has_permission(request, None):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        if not hasattr(user, 'isNode') or not user.isNode:
            return Response({"error": "Not approved by admin"}, status=status.HTTP_403_FORBIDDEN)

        if comment_id:
            # Decode the comment ID and retrieve the comment
            decoded_comment_id = unquote(comment_id)
            comment = get_object_or_404(Comment, id=decoded_comment_id)
            print("comment: ", comment)
            comment_serializer = CommentSerializer(comment)
        elif author_serial and post_serial and remote_comment_FQID:
            # Retrieve the comment based on author, post, and remote FQID
            print("auther_serial: ", author_serial)
            print("post_serial: ", post_serial)
            print("remote_FQID: ", remote_comment_FQID)
            comment = get_object_or_404(
                Comment,  
                author__author_serial=author_serial, 
                id=remote_comment_FQID,
                post__uuid=post_serial
            )

            print("comment: ", comment)
            comment_serializer = CommentSerializer(comment)
        else:
            return Response({"error": "Invalid parameters"}, status=status.HTTP_400_BAD_REQUEST)

    # Return the serialized comment
    return Response(comment_serializer.data, status=status.HTTP_200_OK)

@api_view(['POST'])
def forward_comment(request, post_FQID=None):
    print("in forward_comment")
    request_data = request.data
    print("request_data: ", request_data)
    print("\npost_author_id: ",request_data['post_author']['id'])
    post_author = get_object_or_404(Author, id=request_data['post_author']['id'])
    print("post_author: ", post_author)

    print("\ncommentor_id: ",request_data['author']['id'])
    commentor = get_object_or_404(Author, id=request_data['author']['id'])    
    print("commentor: ", commentor)

    # check if the post_author is on a remote node
    print("current host: ", f"{request.scheme}://{request.get_host()}")
    if post_author.host == f"{request.scheme}://{request.get_host()}":
        return Response({"error": "Object author is on the current host server"}, status = 400)
    else:
        # find the node that the post_author belongs to
        print("\npost_author.host: ", (post_author.host))
        node_author = Author.objects.filter(host=post_author.host, isNode=True).first()
        print("found node_author: ", node_author)
        if not node_author:
            return Response({"error": "Node Author not found"}, status = 404)
        # forward the comment to the post_author's host
        print("in payload")
        payload = {
            "type": "comment",
            "author": {
                "type": "author",
                "id": request_data['author']['id'],
                "page": request_data['author']['page'],
                "host": request_data['author']['host'],
                "displayName": request_data['author']['displayName'],
                "github": request_data['author']['github'],
                "profileImage": request_data['author']['profileImage']
            },
            "comment": request_data['comment'],
            "contentType": "text/markdown",
            "published": request_data['published'],
            "id": request_data['id'],
            "uuid": request_data['uuid'],
            "post": request_data['post'],
            "likes": {
                "type": "likes",
                "page": request_data['likes']['page'],
                "id":   request_data['likes']['id'],
                "size": 50,
                "count": 0,
                "src": []   
            }
        }
        print("payload: ", payload)
        print(node_author.displayName, node_author.first_name, post_author.id+'/inbox')
        # using http basic auth to authenticate with the node server using the node_author's username and password
        headers = {
                "Authorization": f"Basic {base64.b64encode(f'{node_author.displayName}:{node_author.first_name}'.encode()).decode()}",
                "Content-Type": "application/json",
                "host": node_author.host.split('//')[1].replace('/api', ''),
            }
        print("headers: ",headers)
        print("username: ", node_author.displayName)
        print("password: ", node_author.first_name)
        
        print("sending request...", (post_author.id + '/inbox'))
        requestURL = (post_author.id + '/inbox')
        # Construct the remote node's inbox URL using the node_author's host
        response = requests.post(requestURL, json=payload, headers=headers)
        print("response was: ", response)
        print("response returned with code: ",response.status_code)
        print("requestedURL was:",requestURL)

        return Response({
            "object_author_id": post_author.id,
            "response": {
                "status_code": response.status_code,
                "text": response.text,
            },
            "message": "comment forwarded to remote author",
        }, status=200)

class CommentPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'size'
    max_page_size = 5

    def get_paginated_response(self, data):
        return Response({
            'type': 'comments',
            'page_number': self.page.number,
            'size': self.page.paginator.per_page,
            'count': self.page.paginator.count,
            'src': data,
        })

@api_view(['GET'])
def get_posts_comments(request, author_serial=None, post_id=None, post_FQID=None):
    if request.user.is_authenticated:
        # Local user
        if post_FQID:
            # Decode the FQID to find the post ID
            decoded_FQID = unquote(post_FQID)
            post = get_object_or_404(Post, id=decoded_FQID)
        else:
            # Fetch the post using author_id and post_id
            post = get_object_or_404(Post, uuid=post_id)
        # Retrieve comments for the post
        comments = Comment.objects.filter(post=post).order_by('-published')
    else:
        auth = BasicAuthentication()
        user, auth_status = auth.authenticate(request)
        if not user or not IsAuthenticated().has_permission(request, None):
                return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.isNode:
            return Response({"error": "Not approved by admin"}, status=status.HTTP_403_FORBIDDEN)
        if post_FQID:
            # Decode the FQID to find the post ID
            decoded_FQID = unquote(post_FQID)
            post = get_object_or_404(Post, id=decoded_FQID)
        else:
            # Fetch the post using author_id and post_id
            post = get_object_or_404(Post, uuid=post_id)

        # Retrieve comments for the post
        comments = Comment.objects.filter(post=post).order_by('-published')

    # Create an instance of the pagination class
    paginator = CommentPagination()
    paginated_comments = paginator.paginate_queryset(comments, request)

    # Serialize the paginated comments
    serializer = CommentSerializer(paginated_comments, many=True)

    # Return the paginated response
    return paginator.get_paginated_response(serializer.data)

@api_view(['GET', 'POST'])
def get_author_comments(request, author_serial=None, id=None):
    print("author_serial:", author_serial)

    # Determine if the author is specified by UUID or FQID
    if author_serial:
        print("1")
        print("author_serial:", author_serial)
        author = get_object_or_404(Author, author_serial=author_serial)
        print("author: ", author)
    elif id:
        print("2")
        author = get_object_or_404(Author, id=id)
    print("done1")

    if request.method == 'GET':
        # Check if the request is from a local or remote user
        print("user: ", request.user)
        if request.user.is_authenticated:
            # Local user: return all comments by the author
            # Retrieve comments by the specified author
            comments = Comment.objects.filter(author=author)
        else:
            # Remote user request handling
            auth = BasicAuthentication()
            user, auth_status = auth.authenticate(request)

            if not user or not IsAuthenticated().has_permission(request, None):
                return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

            # Check if the authenticated user is an approved remote node
            if not hasattr(user, 'isNode') or not user.isNode:
                return Response({"error": "Not approved by admin"}, status=status.HTTP_403_FORBIDDEN)
            
            comments = Comment.objects.filter(author=author)
            # Remote users: Filter comments to include only those on public or unlisted posts
            comments = comments.filter(post__visibility__in=["PUBLIC", "UNLISTED"])

        # Apply pagination
        paginator = CommentPagination()
        paginated_comments = paginator.paginate_queryset(comments, request)

        # Serialize the paginated data
        serializer = CommentSerializer(paginated_comments, many=True)

        # Return the paginated response
        return paginator.get_paginated_response(serializer.data)

    elif request.method == 'POST':
        # Add a new comment for the specified author on a post
        data = request.data
        if data.get('type') != 'comment':
            return Response({'error': 'Invalid data type. Expected "comment".'}, status=status.HTTP_400_BAD_REQUEST)

        post_id = data.get('post')
        post = get_object_or_404(Post, uuid=post_id)

        serializer = CommentSerializer(data=data)
        if serializer.is_valid():
            serializer.save(author_serial=author_serial, post=post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
# @authentication_classes([BasicAuthentication, SessionAuthentication])
# @permission_classes([IsAuthenticated])
def get_commented_comment(request, author_serial=None, comment_id=None, FQID=None):
    print("comment_uuid: ", comment_id)
    print("author_serial: ", author_serial)
    if author_serial and comment_id:
        if request.user.is_authenticated:
            # Local user: return all comments by the author
            # Retrieve comments by the specified author
            comment = get_object_or_404(Comment, uuid=comment_id, author__author_serial=author_serial)
        else:
            # Get the comment by author and comment UUIDs
            auth = BasicAuthentication()
            user, auth_status = auth.authenticate(request)
            if not user or not IsAuthenticated().has_permission(request, None):
                    return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
            if not user.isNode:
                return Response({"error": "Not approved by admin"}, status=status.HTTP_403_FORBIDDEN)
            
            comment = get_object_or_404(Comment, uuid=comment_id, author__author_serial=author_serial)

    # Handle URL: /api/commented/{COMMENT_FQID}
    elif FQID:
        # Get the comment by its FQID
        comment = get_object_or_404(Comment, id=FQID)

    else:
        # If neither case matches, return a 400 error
        return Response({'error': 'Invalid parameters.'}, status=status.HTTP_400_BAD_REQUEST)

    # Serialize the comment and return the response
    serializer = CommentSerializer(comment)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def api_create_like(request, author_serial):
    # Get the post_id from form data
    post_id = request.data['post_id']
    comment_id = request.data['comment_id']
    #sender = request.POST.get('sender')

    token = request.COOKIES.get('jwt')
    if not token:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        username = payload['id']  # Assuming 'id' is the username or display name
        user = get_object_or_404(Author, displayName=username)
    except jwt.ExpiredSignatureError:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        if post_id:
            post = get_object_or_404(Post, uuid=post_id)
            
            # Check if a like already exists
            if Like.objects.filter(username=username, post=post).exists():
                likes = Like.objects.filter(username=username, post=post)
                return redirect(request.META.get('HTTP_REFERER'))

            try:
                # Ensure post has a likes collection or create one
                if not post.likes_collection:
                    likes_collection = Likes.objects.create()
                    post.likes_collection = likes_collection
                    post.save()

                # Create and save the new Like instance
                like = Like(username=username, post=post, author=user)
                like.save()
                # Add the like to the post's likes collection
                post.likes_collection.add_like(like)
                like_serializer = LikeSerializer(like)
                # Prepare the payload
                published_as_string = like.published.isoformat()
                if hasattr(user, 'host') and not user.host.endswith('/api/'):
                    user.host = user.host.rstrip('/') + '/api/'
                
                payload = {
                    "type": "like",
                    "author": {
                        "type": "author",
                        "id": user.id,
                        "host": user.host,
                        "displayName": user.displayName,
                        "page": user.page,
                        "github": user.github,
                        "profileImage": user.profileImage,
                    },
                    "published": published_as_string,
                    "id": like.id,
                    "object": like.object,
                }
                
                print("payload to send local like:",payload)
                # Send the like to remote nodes
                send_like_to_remote_nodes(like, payload, user)
                print("All likes sent successfully")


                # Returning JSON for Ajax or redirect
                if request.accepts('application/json'):
                    return Response(like_serializer.data, status=status.HTTP_201_CREATED)
                else:
                    #return redirect('viewPost', id=post.uuid)
                    return redirect(request.META.get('HTTP_REFERER'))
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


        elif comment_id:
            comment = get_object_or_404(Comment, id=comment_id)

            # Check if a like already exists
            if Like.objects.filter(username=username, comment=comment).exists():
                return redirect(request.META.get('HTTP_REFERER'))
                    

            try:
                # Ensure post has a likes collection or create one
                if not comment.likes_collection:
                    likes_collection = Likes.objects.create()
                    comment.likes_collection = likes_collection
                    comment.save()

                # Create and save the new Like instance
                like = Like(username=username, comment=comment, author=user)
                like.save()

                # Add the like to the post's likes collection
                comment.likes_collection.add_like(like)
                print("level3")
                like_serializer = LikeSerializer(like)

                # Returning JSON for Ajax or redirect
                if request.accepts('application/json'):
                    return Response(like_serializer.data, status=status.HTTP_201_CREATED)
                else:
                    #return redirect('viewPost', id=post.uuid)
                    return redirect(request.META.get('HTTP_REFERER'))
           
                #Inbox(receiver=author, type='like', FQIDorId=parsed_data['object']['id'], received_at=timezone.now()).save()

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        

        else:
            return Response({"error": "Post ID or Comment ID not found"}, status=status.HTTP_400_BAD_REQUEST)


    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def send_like_to_remote_nodes(like, payload, user):
    """
    Send like notification to all relevant remote nodes.
    """
    recipients = set()

    # Determine the author of the liked object (post or comment)
    object_author = user

    if not object_author:
        logging.error("Object author not found")
        return

    # Get followers or other visibility-related recipients if needed
    followers = Following.get_followers(object_author)
    friends = Following.objects.filter(
        author2=object_author,
        status='accepted'
    ).select_related('author1')

    recipients.update([f.author1 for f in followers])
    recipients.update([f.author1 for f in friends])

    # Send to remote nodes
    nodes = Author.objects.filter(isNode=True)
    for recipient in recipients:
        for node in nodes:
            if object_author.host.endswith('/api/'):
                object_author.host = object_author.host.split('/api/')[0]

            if recipient.host == node.host and recipient.host != like.author.host:
                try:
                    # Prepare headers for the request
                    headers = {
                        "Authorization": f"Basic {base64.b64encode(f'{node.displayName}:{node.first_name}'.encode()).decode()}",
                        "Content-Type": "application/json",
                        "host": node.host.split('//')[1],
                        "X-original-host": "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
                    }

                    recipient_uuid = recipient.id.split('/')[-1]
                    print("Sending like to recipient:", recipient_uuid)

                    # Send like payload to the recipient's inbox
                    response = requests.post(
                        f"{recipient.host}/api/authors/{recipient_uuid}/inbox",
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                except Exception as e:
                    logging.error(f"Failed to send like to {recipient.host}: {str(e)}")
                    if hasattr(e, 'response'):
                        logging.error(f"Response content: {e.response.content}")
                    continue


# Construct posts object for home page
class PostPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'type': 'posts',
            'page_number': self.page.number,
            'size': self.page.paginator.per_page,
            'count': self.page.paginator.count,
            'src': data,
        })

@api_view(['GET', 'POST'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_posts_create_post(request, author_serial):
    """Handles both fetching posts for home page and creating post"""

    if request.method == 'GET':
        author = get_object_or_404(Author, author_serial=author_serial)
        posts = Post.objects.all().order_by('-published')

        paginator = PostPagination()
        result_page = paginator.paginate_queryset(posts, request)

        # Filter posts based on visibility to the current user
        visible_posts = [post for post in result_page if post.is_visible_to(request.user)]
        serializer = PostSerializer(visible_posts, many=True)

        # Adjust the count to reflect only the visible posts
        paginated_response = paginator.get_paginated_response(serializer.data)
        paginated_response.data['count'] = len(visible_posts)

        return paginated_response

    elif request.method == 'POST':
        token = request.COOKIES.get('jwt')
        if not token:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            author = get_object_or_404(Author, displayName=payload['id'])
            if hasattr(author, 'host') and not author.host.endswith('/api/'):
                author.host = author.host.rstrip('/') + '/api/'
        except jwt.ExpiredSignatureError:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        except Author.DoesNotExist:
            return Response({"error": "Author not found"}, status=status.HTTP_404_NOT_FOUND)

        # Extract post data from request
        title = request.POST.get('title')
        description = request.POST.get('description')
        contentType = request.POST.get('contentType')
        visibility = request.POST.get('visibility')
        content = request.POST.get('content', '')
        image = request.FILES.get('img')
        type = 'post'

        if contentType and contentType.startswith('image/') and image:
            # Read the image file and encode it as base64
            image_data = image.read()
            encoded_image = base64.b64encode(image_data).decode('utf-8')
            content = f"data:{image.content_type};base64,{encoded_image}"

        # Create a new post associated with the current author
        post = Post(
            type=type,
            title=title,
            description=description,
            contentType=contentType,
            content=content,
            visibility=visibility,
            author=author,  # Use the author from the token
        )
        post.save()
        if "/api//" in post.id:
            # Get the existing post and delete it
            old_id = post.id
            new_id = old_id.replace("/api//", "/", 1)
            # Update the ID in the database directly
            Post.objects.filter(id=old_id).update(id=new_id)
            post = Post.objects.get(id=new_id)
        print("author111: ", author)
        print("author_id111: ", post.author.id)

        # Serialize the post and return the response
        serializer = PostSerializer(post)
        
        # Send the post to remote nodes if visibility is public, unlisted, or friends
        send_post_to_remote_nodes(post, serializer.data, 'new')
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['POST'])
def repost_post(request, id):
    post = get_object_or_404(Post, uuid=id)

    if request.method == 'POST':
        # Extract the author from the JWT token
        token = request.COOKIES.get('jwt')
        if not token:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            author = get_object_or_404(Author, displayName=payload['id'])
        except jwt.ExpiredSignatureError:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        except Author.DoesNotExist:
            return Response({"error": "Author not found"}, status=status.HTTP_404_NOT_FOUND)

        # Use the existing post object to create a new post
        new_post = Post(
            title=f"{post.title}(Reposted: {post.author.displayName})",  # Add "Reposted:" to the title
            description=post.description,
            contentType=post.contentType,
            content=post.content,
            visibility=post.visibility,  # You can choose to change this if needed
            author=author,  # Use the author from the token
            type='repost'
        )
        
        new_post.save()

        # Serialize the new post and return the response
        serializer = PostSerializer(new_post)
        # return Response(serializer.data, status=status.HTTP_201_CREATED)
        return redirect('home_page')  # Redirect after successful repost

    return Response({"error": "Invalid request method"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def repost_link(request, id):
    post = get_object_or_404(Post, uuid=id)

    if request.method == 'POST':
        # Extract the author from the JWT token
        token = request.COOKIES.get('jwt')
        if not token:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            author = get_object_or_404(Author, displayName=payload['id'])
        except jwt.ExpiredSignatureError:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        except Author.DoesNotExist:
            return Response({"error": "Author not found"}, status=status.HTTP_404_NOT_FOUND)

        # Use the original post title and URL for the new repost
        # Get the current URL
        current_url = request.build_absolute_uri(request.path)
        
        # Remove the last part of the path
        base_url = '/'.join(current_url.split('/')[:-2])  # This removes the last two segments

    
        new_post = Post(
            title=f"Repost: {post.title}",  # Repost title
            description="",  # Optional description
            contentType="text/plain",  # Assuming you're using plain text for links
            #content=f"{request.build_absolute_uri(post.get_absolute_url())}",  # Set the content to the post link
            content = f"{base_url}",
            visibility=post.visibility,
            author=author,
        )
        
        new_post.save()

        # Serialize the new post and return the response
        serializer = PostSerializer(new_post)
        return redirect('home_page')  # Redirect after successful repost

    return Response({"error": "Invalid request method"}, status=status.HTTP_400_BAD_REQUEST)

def view_edit_post(request, fqid):
    post = get_object_or_404(Post, id=fqid)
    author_id = get_author_from_cookie(request).data.get('id')
    return render(request, 'posts/editPost.html', {'post': post, 'author_id': author_id})

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_edit_delete_post(request, author_serial, post_id):
    print("in edit post API")
    post = get_object_or_404(Post, uuid=post_id)
    try:
        # Make sure user who is not the author can't edit/delete the post
        if author_serial != post.author.author_serial and request.method in ["PUT", "DELETE"]:
            return Response({"error": "Unauthorized to edit/delete other author's post"}, status=status.HTTP_403_FORBIDDEN)
    except jwt.ExpiredSignatureError:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        print("in GET")
        if post.visibility == 'PUBLIC':
            serializer = PostSerializer(post)
            return Response(serializer.data, status=status.HTTP_200_OK)
        # Check for authentication and friendship for "friends-only" posts
        if post.visibility == 'FRIENDS':
            if request.user.is_authenticated and Following.are_friends(request.user, post.author):
                serializer = PostSerializer(post)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Unauthorized to view friends-only post"}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'PUT':
        print("in PUT")
        data = request.data.copy()  # Safely copy the data
        image = request.FILES.get('img')
        print("data: ", data)
        print("image: ", image)

        # Handle image upload
        if image:
            print("in image upload")
            # Read and encode the image in base64
            image_data = image.read()
            encoded_image = base64.b64encode(image_data).decode('utf-8')
            # Set the encoded image as the content
            data['content'] = f"data:{image.content_type};base64,{encoded_image}"
            serializer = PostSerializer(post, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                # Send the updated post to remote nodes
                send_post_to_remote_nodes(post, serializer.data, action_type='edit')
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            print("returning original content")
            # Retain the original content if no new content is provided
            if not data.get('content'):
                data['content'] = post.content
            serializer = PostSerializer(post, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                # Send the updated post to remote nodes
                send_post_to_remote_nodes(post, serializer.data, action_type='edit')
            return Response(serializer.data, status=status.HTTP_200_OK)
        print("finished in PUT")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        # Ensure that only the author of the post or an admin can delete the post
        if post.author == request.user or request.user.is_superuser:
            # Notify remote nodes about post deletion if it was previously shared
            post_serializer = PostSerializer(post)
            send_post_to_remote_nodes(post, post_serializer.data, action_type='delete')
            post.visibility = 'DELETED'  # Mark the post as 'DELETED'
            post.save()
            return Response({"message": "Post deleted successfully"}, status=status.HTTP_200_OK)
        else:
            # If the user is not the author
            return Response({"error": "Unauthorized to delete this post"}, status=status.HTTP_403_FORBIDDEN)
    return Response({"error": "Method not allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
def get_post_image(request, author_serial=None, post_id=None, FQID=None):
    print("in")
    if request.user.is_anonymous:
        # If author_id and post_id are provided, retrieve the post by post_id
        if author_serial:
            print("gettiing post ...")
            # Retrieve the post using both author_id and post_id
            post = get_object_or_404(Post, uuid=post_id, author__author_serial=author_serial)
            print("got post")
            print("post: ", post.uuid)
        elif FQID:
            post = get_object_or_404(Post, id=FQID)
        else:
            return Response({'error': 'Post ID or FQID must be provided'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        auth = BasicAuthentication()
        user, auth_status = auth.authenticate(request)
        if not user or not IsAuthenticated().has_permission(request, None):
                return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.isNode:
            return Response({"error": "Not approved by admin"}, status=status.HTTP_403_FORBIDDEN)
        # If author_id and post_id are provided, retrieve the post by post_id

        if author_serial:
            print("gettiing post ...")
            # Retrieve the post using both author_id and post_id
            post = get_object_or_404(Post, uuid=post_id, author__author_serial=author_serial)
            print("got post")
            print("post: ", post.uuid)
        elif FQID:
            post = get_object_or_404(Post, id=FQID)
        else:
            return Response({'error': 'Post ID or FQID must be provided'}, status=status.HTTP_400_BAD_REQUEST)


    # Check if the content type is a base64 image
    if post.contentType in ['image/png;base64', 'image/jpeg;base64']:
        print("getting image ...")
        try:
            # Extract the base64 data after the comma
            encoded_data = post.content.split(',', 1)[1]
            # print("encoded_DATA: ", encoded_data)
            # Decode the base64 content
            image_data = base64.b64decode(encoded_data)
            
            # Set the appropriate MIME type for the response
            mime_type = 'image/png' if 'png' in post.contentType else 'image/jpeg'
            
            # Return the binary image data in the response
            return HttpResponse(image_data, content_type=mime_type)
        
        except base64.binascii.Error:
            # Handle decoding error
            return Response({'error': 'Invalid base64 image data', 'content': post.content}, status=status.HTTP_400_BAD_REQUEST)
    else:
        # If the content is not an image, return a 404 or error response
        return Response({'error': 'Image not found or content type is not an image', 'post.contentType': post.contentType}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def get_post_FQID(request, FQID=None):
    if FQID:
        post = get_object_or_404(Post, id=FQID)
        if post.visibility == 'PUBLIC':
            serializer = PostSerializer(post)
            return Response(serializer.data, status=status.HTTP_200_OK)
        # Check for authentication and friendship for "friends-only" posts
        if post.visibility == 'FRIENDS':
            if request.user.is_authenticated and Following.are_friends(request.user, post.author):
                serializer = PostSerializer(post)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Unauthorized to view friends-only post"}, status=status.HTTP_403_FORBIDDEN)
    else:
        return Response({'error': 'FQID must be provided'}, status=status.HTTP_400_BAD_REQUEST)
    
def view_post(request, fqid):
    post = get_object_or_404(Post, id=fqid)

    # Check for post visibility
    if post.visibility == 'DELETED' and not request.user.is_staff:  # Only admins can see deleted posts
        return redirect('home_page')  # Redirect non-admins to the home page

    if post.visibility == 'PRIVATE' and not request.user.is_authenticated:  # Private posts require authentication
        return redirect('login')  # Redirect unauthenticated users to login

    if post.visibility == 'UNLISTED' or post.visibility == 'PUBLIC':
        # Allow access for public and unlisted posts without authentication
        pass
    else:
        # For all other posts, ensure the user is authenticated
        if not request.user.is_authenticated:
            return redirect('login')

    author = post.author
    comments = post.comments.all()

    # Extract the author from the JWT token
    token = request.COOKIES.get('jwt')
    if not token and (post.visibility != 'PUBLIC' and post.visibility != 'UNLISTED'):
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    if token:
        try:
            # Decode the JWT token and get the author's display name
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            displayName = payload['id']  # Assuming 'id' holds the displayName or appropriate user identifier
        except jwt.ExpiredSignatureError:
            return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.DecodeError:
            return Response({"error": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)
        except Author.DoesNotExist:
            return Response({"error": "Author not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'POST':
        # Retrieve the form data
        username = displayName if token else "Anonymous"  # Assign anonymous for public/unlisted without JWT
        content = request.POST.get('content')

        # Create and save the new comment
        comment = Comment(username=username, content=content, post=post)
        comment.save()

        # Redirect to the same post after adding the comment (prevents form resubmission on refresh)
        return redirect('viewPost', id=post.uuid)

    return render(request, "posts/viewPost.html", {"id": id, "post": post, "author": author, "comments": comments})

@api_view(['GET'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def api_view_postLikes(request, author_serial, post_id):
    post = get_object_or_404(Post, uuid=post_id)

    if post.visibility == 'DELETED' and not request.user.is_staff:
        # Non-admin users should not see deleted posts
        return redirect('home_page')  # Redirect to index or a 404 page

    author = get_object_or_404(Author, author_serial=author_serial)

    
    
    # Check if the author is a node
    if author.isNode:
        try:
            # Prepare request data to be sent to the remote node
            endpoint = f"{author.host}/api/authors/{author_serial}/posts/{post_id}/likes"
            headers = {
                'Content-Type': 'application/json'
            }
            # Assume `displayName` and `password` are available for basic authentication
            response = requests.get(
                endpoint,
                headers=headers,
                auth=HTTPBasicAuth(author.displayName, author.password)
            )

            response.raise_for_status()  # Raise an exception for any HTTP error responses
            likes_data = response.json()  # Parse the response data

            # Optionally, you can add custom handling for the response data here

        except requests.RequestException as e:
            # Handle connection errors, timeouts, etc.
            logging.error(f"Failed to fetch data from node {author.host}: {e}")
            likes_data = {"error": "Failed to fetch data from remote node"}
            # You might decide to return an error response or handle it differently here

        # Render a template or return a response based on `likes_data`
        return render(request, "posts/viewPostLikes.html", {"post_id": post_id, "post": post, "author": author, "likes_data": likes_data})

    # If not a node, proceed with regular rendering logic
    return render(request, "posts/viewPostLikes.html", {"post_id": post_id, "post": post, "author": author})



@api_view(['GET'])
def api_view_Likes(request, post_id):
    post = get_object_or_404(Post, uuid=post_id)

    if post.visibility == 'DELETED':    # TODO: add "and user is not admin"
        # Non-admin users should not see deleted posts
        return redirect('home_page')  # Redirect to index or a 404 page

    author = post.author.author_serial

    return render(request, "posts/viewPostLikes.html", {"post_id": post_id, "post": post, "author": author})

@api_view(['GET'])
def api_view_Likes_comments(request, author_serial, post_id, comment_id):
    print("Reached comment likes")
    comment = get_object_or_404(Comment, id=comment_id)

    print("original post_id: ", post_id)
    post_id = Post.objects.filter(
        comments__id=comment_id  # Use the related name for the reverse relationship
    ).values_list('id', flat=True).first()
    print("queried post_id: ", post_id)

    if not post_id:
        return Response({"error": "No matching post found for the given author and comment."}, status=404)

    post = get_object_or_404(Post, id=post_id)
    author = comment.author

    
    # If not a node, proceed with regular rendering logic
    return render(request, "posts/viewCommentLikes.html", {
        "comment_id": comment_id, 
        "comment": comment, 
        "author": author,
        "post_id": post_id,  # If needed in the template
        "post": post
    })

@api_view(['POST'])
def github_post(request, author_serial):
    author = get_object_or_404(Author, author_serial=author_serial)
    data = request.data
    check = githubPostIds.objects.filter(id=data['id'])
    if check:
        return Response({"error": "Post already exists"}, status=status.HTTP_208_ALREADY_REPORTED)
    post = Post(
        title=data['title'],
        description=data['description'],
        contentType=data['contentType'],
        content=data['content'],
        visibility=data['visibility'],
        author=author
    )
    post.save()
    githubPost = githubPostIds(id=data['id'], post=post)
    githubPost.save()

    return Response(data, status=status.HTTP_200_OK)

def get_base_recipients(post):
    """Get base followers and friends for a post's author"""
    followers = Following.get_followers(post.author)
    friends = [f.author1 for f in Following.objects.filter(
        author2=post.author, 
        status='accepted'
    ) if Following.is_following(f.author2, f.author1)]
    return [f.author1 for f in followers], friends

def send_post_to_remote_nodes(post, serializer_data, action_type='new'):
    """Send post to remote nodes based on visibility and action type"""
    recipients = set()
    
    # Get base recipients based on visibility
    if post.visibility in ['PUBLIC', 'UNLISTED']:
        followers = Following.get_followers(post.author)
        friends = Following.objects.filter(
            author2=post.author, 
            status='accepted'
        ).select_related('author1')
        
        recipients.update([f.author1 for f in followers])
        if post.visibility == 'PUBLIC':
            recipients.update([f.author1 for f in friends])
            
    elif post.visibility == 'FRIENDS':
        friends = Following.objects.filter(
            author2=post.author,
            status='accepted'
        ).select_related('author1')
        recipients.update([f.author1 for f in friends])
            
    if action_type in ['edit', 'delete']:
        # For edit/delete, send to previous recipients
        previous_recipients = Inbox.objects.filter(
            FQIDorId=post.id,
            type='post'
        ).select_related('receiver')
        for inbox_entry in previous_recipients:
            recipients.add(inbox_entry.receiver)
    if action_type == 'delete':
        serializer_data['visibility'] = 'DELETED'
    print("sending to previous recipients", recipients)
    # Send to each remote recipient's inbox
    nodes = Author.objects.filter(isNode=True)
    for recipient in recipients:
        for node in nodes:
            if post.author.host.endswith('/api/'):
                post.author.host = post.author.host.split('/api/')[0]
            print("recipient.host: ", recipient.host)
            print("node.host: ", node.host)
            print("post.author.host: ", post.author.host)
            
            
            if recipient.host == node.host and recipient.host != post.author.host:
                try:
                    # For edit actions, update existing inbox entry
                    if action_type == 'edit' or action_type == 'delete':
                        Inbox.objects.filter(
                            FQIDorId=post.id,
                            receiver=recipient,
                            type='post'
                        ).update(received_at=timezone.now())
                    # else:
                    #     # For new posts, create new inbox entry
                    #     Inbox.objects.create(
                    #         receiver=recipient,
                    #         type='post',
                    #         FQIDorId=post.id,
                    #         received_at=timezone.now()
                    #     )
                    recipient_uuid = recipient.id.split('/')[-1]
                    print("recipient id: ", recipient_uuid)
                    print("serializer_data: ", serializer_data)
                    if isinstance(serializer_data, dict) and 'author' in serializer_data:
                        print('first condition met')
                        if not serializer_data['author']['host'].endswith('/api/'):
                            print('second condition met')
                            serializer_data['author']['host'] = serializer_data['author']['host'] + '/api/'
                            print("serializer_data['author']['host']: ", serializer_data['author']['host'])
                    # Send to remote node using recipient's author_serial
                    response = requests.post(
                        f"{recipient.host}/api/authors/{recipient_uuid}/inbox",
                        json=serializer_data,
                        headers={
                            "Authorization": f"Basic {base64.b64encode(f'{node.displayName}:{node.first_name}'.encode()).decode()}",
                            'Content-Type': 'application/json',
                            'host': node.host.split('//')[1],
                            'X-original-host':  "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
                        }
                    )
                    response.raise_for_status()
                    
                except Exception as e:
                    logging.error(f"Failed to send post to {recipient.host}: {str(e)}")
                    if hasattr(e, 'response'):
                        logging.error(f"Response content: {e.response.content}")
                    continue