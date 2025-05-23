from django.shortcuts import render, get_object_or_404, redirect
from rest_framework.response import Response
from django.utils.dateformat import format
from rest_framework import status
import jwt
from django.conf import settings
from .models import Notification
from rest_framework.decorators import api_view, action,authentication_classes, permission_classes
from author.models import Author, FollowRequest
from django.contrib.contenttypes.models import ContentType
from posts.models import Post, Comment, Like, Likes
from posts.serializers import PostSerializer
from django.conf import settings
import json
from author.models import Following
from author.serializers import AuthorSerializer
from .models import Inbox
from django.utils import timezone
import logging
from urllib.parse import unquote
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from author.serializers import AuthorSerializer
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from posts.serializers import LikeSerializer
from rest_framework.permissions import IsAuthenticated
import requests
import base64
from django.views.decorators.csrf import csrf_exempt

@api_view(['GET'])
def inbox(request):
    token = request.COOKIES.get('jwt')
    if not token:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        author = get_object_or_404(Author, displayName=payload['id']) # author that sent the request

        # Get follow requests, comments, and likes as querysets
        follow_req_notifications = Following.objects.filter(author2=author, status='pending')
        posts = Post.objects.filter(author=author)
        comments = Comment.objects.filter(author=author)
        comment_notifications = Comment.objects.filter(post__in=posts)
        like_notifications = Like.objects.filter(post__in=posts) | Like.objects.filter(comment__in=comments)

        
        # Get the list of authors that the current user is following
        followed_authors = Following.objects.filter(author1=author).values_list('author2', flat=True)
        # Filter for repost notifications where the author is in the list of followed authors
        repost_notifications = Post.objects.filter(author__in=followed_authors, type="repost")

        # Serialize the querysets to JSON-serializable data
        
        follow_requests_data = list(follow_req_notifications.values('id', 'author1__id', 'author2__id', 'author1__displayName','author1__profileImage','date'))
        comment_data = list(comment_notifications.values('id', 'username', 'comment', 'published', 'post__title', 'author__profileImage', 'author__displayName'))
        like_data = list(
            like_notifications.values(
                'uuid',
                'username',
                'post__title',       # For likes on posts
                'comment__comment',  # For likes on comments (assuming 'content' is the field for comment text)
                'published',
                'author__displayName',
                'author__profileImage'
            )
        )
        repost_data = list(repost_notifications.values('id', 'author__displayName', 'content', 'title', 'author__profileImage'))

        # Send the data to the template
        for follow_request in follow_requests_data:
            follow_request['author1__profileImage'] = author.host + settings.MEDIA_URL +follow_request['author1__profileImage']
            author_id = follow_request['author1__id']
            author = get_object_or_404(Author, id=author_id)
            follow_request['profileImage'] = author.profileImage        
        for comment in comment_data:
            comment['author__profileImage'] = author.host + settings.MEDIA_URL + comment['author__profileImage']
            username = comment['username']
            author = get_object_or_404(Author, displayName=username)
            comment['profileImage'] = author.profileImage 
        for like in like_data:
            like['author__profileImage'] = author.host + settings.MEDIA_URL + like['author__profileImage']
            username = like['username']
            author = get_object_or_404(Author, displayName=username)
            like['profileImage'] = author.profileImage 
        for repost in repost_data:
            repost['author__profileImage'] = author.host + settings.MEDIA_URL + repost['author__profileImage']
            username = repost['author__displayName']
            author = get_object_or_404(Author, displayName=username)
            repost['profileImage'] = author.profileImage 
        
        context = {
            'follow_requests': follow_requests_data,
            'comments': comment_data,
            'likes': like_data,
            'reposts': repost_data
        }

        return render(request, 'inbox/inbox.html', context)

    except jwt.ExpiredSignatureError:
        return Response({"error": "Unauthenticated"}, status=401)
    except jwt.InvalidTokenError:
        return Response({"error": "Invalid token"}, status=401)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)
    
@api_view(['POST'])
def inboxApi(request, object_author_serial):
    print("stage1 logic")
    token = request.COOKIES.get('jwt')
    flag = 1   # flag to check if the request is from my nodes frontend
    payload, author, actor, object_author = None, None, None, None
    if not token:
        print("stage3 logic")
        flag = 0
        auth = BasicAuthentication()
        user, auth_status = auth.authenticate(request)
        if  not user or not IsAuthenticated().has_permission(request, None):
            
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        
    
    try:
        if flag == 1:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            author = get_object_or_404(Author, displayName=payload['id']) # author that sent the request

        # Parse JSON string into a Python dictionary
        parsed_data = request.data
        print("parsed data")
        print(parsed_data)

        # check the type of request object
        if parsed_data['type'] == 'follow':
            try:
                if parsed_data['object']['host'] != parsed_data['actor']['host']:
                    
                    objectAuthor = get_object_or_404(Author, id=parsed_data['object']['id'])
                    print("object author 11", objectAuthor)
                    print(parsed_data['actor']['id'])
                    if parsed_data['actor']['host'].endswith('/api/'):
                        parsed_data['actor']['host'] = parsed_data['actor']['host'][:-5]
                    actorSerializer = AuthorSerializer(data=parsed_data["actor"], partial=True)

                    if actorSerializer.is_valid():
                        actorSerializer.save()
                    # else:
                    #     return Response({"error": "Invalid object author data","serializer":actorSerializer.errors}, status=400)
                    actor = Author.objects.get(id=parsed_data['actor']['id'])
                    if not actor:
                        return Response({"error": "Actor not found"}, status=404)
                else:
                    actor = get_object_or_404(Author, id=parsed_data['actor']['id'])
                    objectAuthor = get_object_or_404(Author, id=parsed_data['object']['id'])
                    # check if the actor is already following the object_author
                    if actor.id == objectAuthor.id:
                        return Response({"error": "Cannot follow yourself"}, status=400)
                new = Following.follow(actor, objectAuthor)
                if not new:
                    return Response({"error": "Already following"}, status=400)
                
                inboxxx = Inbox(receiver=objectAuthor, type='follow', FQIDorId=new.id, received_at=timezone.now()).save()

                return Response({"message": "Follow request sent","requestStatus":new.status}, status=200)


            
            except Author.DoesNotExist:
                # forward the request to the next host server if host is not the current host
                # if actor does not exist create it and send a follow request to the object_author
                # if object_author does not exist forward the request to the next host server inbox
                return Response({"error": "Actor not found"}, status=404)
            
        elif parsed_data['type'] == 'comment':
            print("organizing comment in inbox")

            # Get the post instance using the post URL
            post_id = parsed_data['post']
            print("post_id: ", post_id)
            post = get_object_or_404(Post, id=post_id)  # Retrieve the Post instance
            post_author_id = post.author.id
            print("post.id: ", post.id)
            print("post.title: ", post.title)

            author_id = parsed_data['author']['id']
            author = get_object_or_404(Author, id=author_id)

            # Check if the comment already exists based on UUID
            comment_id = parsed_data['id']
            print("comment_id: ", comment_id)
            # comment_uuid = parsed_data['id'].split('/')[-1]
            if Comment.objects.filter(id=comment_id).exists():
                return Response({"message": "Comment already exists"}, status=status.HTTP_200_OK)

            # forward the comment to the remote post_author's inbox
            post_author = Author.objects.get(id=post_author_id)
            Inbox(receiver=post_author, type='comment', FQIDorId=parsed_data['id'], received_at=timezone.now()).save()

            comment = Comment(author=author, username=parsed_data['author']['displayName'], comment=parsed_data['comment'], published=parsed_data['published'], id=parsed_data['id'], post=post)
            print("\nComment: ", comment)

            host = request.get_host()
            comment._host = host  # Set the host as an attribute on the instance
            comment.save()
            print("comment saved")

            post.comments.add(comment)
            print("comment added to respective post")

            return Response({"message": "Comment sent"}, status=200)
        
        elif parsed_data['type'] == 'like':
            print("stage2 logic")
            # Check if 'author' is a string or a dictionary
            if isinstance(parsed_data['author'], str):
                # If 'author' is a string, query using author_serial
                sender_author = Author.objects.filter(author_serial=parsed_data['author']).first()
                if not sender_author:
                    return Response({"error": "Author with the given serial not found"}, status=404)
            else:
                # If 'author' is a dictionary, query using the nested 'id'
                sender_author = Author.objects.filter(id=parsed_data['author'].get('id')).first()
                if not sender_author:
                    return Response({"error": "Author with the given ID not found"}, status=404)

            # Continue processing with sender_author

            object_author = Author.objects.get(author_serial=object_author_serial)
            sender_host = sender_author.host
            object_host = object_author.host
            print("sender host",sender_host)
            print("object host",object_host)
            if sender_host != object_host:
                # Extract object field and determine target
                object_field = parsed_data['object']
                is_comment = "comment" in object_field

                try:
                    if is_comment:
                        # Handle Like for Comment
                        comment_id = object_field
                        comment = get_object_or_404(Comment, id=comment_id)

                        # Check if a like already exists for the comment
                        if Like.objects.filter(username=sender_author.displayName, comment=comment).exists():
                            return Response({"message": "Like already exists for comment"}, status=200)

                        # Ensure the comment has a likes collection or create one
                        if not hasattr(comment, 'likes_collection') or not comment.likes_collection:
                            likes_collection = Likes.objects.create()
                            comment.likes_collection = likes_collection
                            comment.save()

                        # Create and save the Like instance for the comment
                        like = Like(username=sender_author.username, comment=comment, author=sender_author)
                        like.save()

                        # Add the like to the comment's likes collection
                        comment.likes_collection.add_like(like)
                    

                    else:
                        # Handle Like for Post
                        post_id = object_field
                        post = get_object_or_404(Post, id=post_id)

                        # Check if a like already exists for the post
                        if Like.objects.filter(username=sender_author.displayName, post=post).exists():
                            return Response({"message": "Like already exists for post"}, status=200)

                        # Ensure the post has a likes collection or create one
                        if not hasattr(post, 'likes_collection') or not post.likes_collection:
                            likes_collection = Likes.objects.create()
                            post.likes_collection = likes_collection
                            post.save()

                        # Create and save the Like instance for the post
                        like = Like(username=sender_author.displayName, post=post, author=sender_author)
                        like.save()

                        # Add the like to the post's likes collection
                        post.likes_collection.add_like(like)
                        
                        
                except Exception as e:
                    print(f"Error saving like: {e}")
                    return Response({"error": "Failed to save like"}, status=500)
                
            else:
                print("hosts equal")
            #Inbox(receiver=object_author, type='like', FQIDorId=parsed_data['id'], received_at=timezone.now()).save()
            return Response({"message": "Like sent"}, status=200)
        
        elif parsed_data['type'] == 'post':
            # Extract author data from the parsed_data
            author_data = parsed_data.get('author')
            if not author_data:
                return Response({"error": "Author data missing from post"}, status=status.HTTP_400_BAD_REQUEST)
    
            try:
                # Try to get or create the author
                print("author_data: ", author_data)
                if author_data['host'].endswith('/api/'):
                        author_data['host'] = author_data['host'][:-5]
                author, _ = Author.objects.get_or_create(
                    id=author_data.get('id'),
                    defaults={
                        'displayName': author_data.get('displayName'),
                        'host': author_data.get('host'),
                        'github': author_data.get('github', ''),
                        'profileImage': author_data.get('profileImage', '')
                    }
                )
            except Exception as e:
                logging.error(f"Error processing author data: {str(e)}")
                return Response({"error": "Invalid author data"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if post exists
            existing_post = Post.objects.filter(id=parsed_data.get('id')).first()
            
            if existing_post:
                # Update existing post
                serializer = PostSerializer(existing_post, data=parsed_data, partial=True)
            else:
                # Create new post
                print("parsed_data: ", parsed_data)
                serializer = PostSerializer(data=parsed_data,partial=True)

            if serializer.is_valid():
                try:
                    post = serializer.save(author=author)  # Set the author explicitly
                    
                    # Create or update inbox entry
                    Inbox.objects.update_or_create(
                        FQIDorId=post.id,
                        receiver=request.user,
                        defaults={
                            'type': 'post',
                            'received_at': timezone.now()
                        }
                    )
                    
                    return Response({
                        "message": "Post updated" if existing_post else "Post created",
                        "post": serializer.data
                    }, status=status.HTTP_200_OK if existing_post else status.HTTP_201_CREATED)
                    
                except Exception as e:
                    logging.error(f"Error saving post: {str(e)}")
                    return Response({"error": "Error saving post"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except jwt.ExpiredSignatureError:
        return Response({"error": "Unauthenticated"}, status=401)
    except jwt.InvalidTokenError:
        return Response({"error": "Invalid token"}, status=401)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)
    
@api_view(['POST'])
def forward_like_request(request):
    # Get the post_id from form data
    post_id = request.data['post_id']
    comment_id = request.data['comment_id']
    print("receiver id ", request.data['receiver_id'])
    object_author = get_object_or_404(Author, id=request.data['receiver_id'])
    if hasattr(object_author, 'host') and not object_author.host.endswith('/api/'):
                object_author.host = object_author.host.rstrip('/') + '/api/'
    print("authorforforward")
    print(object_author)
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
            print('test1')
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
                # forward the follow request to the object_author's host
                # Convert to string
                published_as_string = like.published.isoformat()

                if hasattr(user, 'host') and not user.host.endswith('/api/'):
                    user.host = user.host.rstrip('/') + '/api/'
                payload = {
                    "type":"like",
                    "author":{
                        "type":"author",
                        "id":user.id,
                        "host":user.host,
                        "displayName":user.displayName,
                        "page":user.page,
                        "github": user.github,
                        "profileImage": user.profileImage
                    },
                    "published": published_as_string,
                    "id": like.id,
                    "object": like.object
                }
                if object_author.host.endswith('/api/'):
                    object_author.host = object_author.host.split('/api/')[0]
                print("object_author.host: ", object_author.host)
                node_author = Author.objects.filter(host=object_author.host, isNode=True).first()
                if not node_author:
                    return Response({"error": "Node author not found"}, status=404)
                print(node_author.displayName, node_author.first_name, object_author.id+'/inbox')
                # using http basic auth to authenticate with the node server using the node_author's username and password
                headers = {
                        "Authorization": f"Basic {base64.b64encode(f'{node_author.displayName}:{node_author.first_name}'.encode()).decode()}",
                        "Content-Type": "application/json",
                        "host": node_author.host.split('//')[1],
                        "X-original-host":  "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
                    }
                print(headers)
                

                response = requests.post(object_author.id + '/inbox', json=payload, headers=headers)
                print(response.status_code, response.text)

                #return Response({"message": "Like request forwarded"}, status=200)
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

                published_as_string = like.published.isoformat()

                
                payload = {
                    "type":"like",
                    "author":{
                        "type":"author",
                        "id":user.id,
                        "host":user.host,
                        "displayName":user.displayName,
                        "page":user.page,
                        "github": user.github,
                        "profileImage": user.profileImage
                    },
                    "published": published_as_string,
                    "id": like.id,
                    "object": like.object
                }
                
                node_author = Author.objects.filter(host=object_author.host, isNode=True).first()
                if not node_author:
                    return Response({"error": "Node author not found"}, status=404)
                print(node_author.displayName, node_author.first_name, object_author.id+'/inbox')
                # using http basic auth to authenticate with the node server using the node_author's username and password
                headers = {
                        "Authorization": f"Basic {base64.b64encode(f'{node_author.displayName}:{node_author.first_name}'.encode()).decode()}",
                        "Content-Type": "application/json",
                        "host": node_author.host.split('//')[1],
                        "X-original-host":  "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
                    }
                print(headers)
                

                response = requests.post(object_author.id + '/inbox', json=payload, headers=headers)
                print(response.status_code, response.text)

                #return Response({"message": "Like request forwarded"}, status=200)
                return redirect(request.META.get('HTTP_REFERER'))


            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        

        else:
            return Response({"error": "Post ID or Comment ID not found"}, status=status.HTTP_400_BAD_REQUEST)


    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'DELETE', 'PUT'])
def handle_follow_request_response(request, author_serial, foreign_author_fqid):
    token = request.COOKIES.get('jwt')
    if not token:
        return Response({"error": "Unauthenticated"}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        author = get_object_or_404(Author, displayName=payload['id']) # author that sent the request

        
        # foreign_author_fqid will be percent encoded, so we need to decode it
        
        foreign_author_fqid = unquote(foreign_author_fqid).rstrip('/')
        print(f"Decoded foreign_author_fqid: {foreign_author_fqid}")
        foreign_author = get_object_or_404(Author, id=foreign_author_fqid)
        if request.method == 'PUT':
            # Accept follow request from foreign_author 
            follow_request = get_object_or_404(Following, author1 = foreign_author, author2 = author, status='pending')
            follow_request.status = 'accepted'
            follow_request.save()
            return Response({"message": "Follow request accepted"}, status=200)
        elif request.method == 'DELETE':
            # Reject follow request from foreign_authorm, status can be 'pending' or 'accepted'
            follow_request = get_object_or_404(Following, author1 = author, author2 = foreign_author)
            follow_request.delete()
            return Response({"message": "Follow request rejected"}, status=200)
        elif request.method == 'GET':
            # Get the follow request from foreign_author
            # check if FOREIGN_AUTHOR_FQID is a follower of AUTHOR_SERIAL Should return 404 if they're not.This is how you can check if follow request is accepted
            follow_request = get_object_or_404(Following, author1 = foreign_author, author2 = author, status='accepted')
            return Response({"message": "Follow request accepted"}, status=200)
    except jwt.ExpiredSignatureError: # redirect to /login
        return redirect('login')

    except jwt.InvalidTokenError: # redirect to /login
        return redirect('login')

@api_view(['POST'])
def forward_follow_request(request):
    ''' This view is used to forward follow requests to the next host server if the object author is not on the current host server '''
    request_data = request.data
    # check if the object author is on the current host server
    object_author = get_object_or_404(Author, id=request_data['object']['id'])
    actor = get_object_or_404(Author, id=request_data['actor']['id'])
    if object_author.host == request.get_host():
        return Response({"error": "Object author is on the current host server"}, status=400)
    else:
        # find author with the same host as object_author and isNode=True

        node_author = Author.objects.filter(host=object_author.host, isNode=True).first()
        if not node_author:
            return Response({"error": "Node author not found"}, status=404)
        # forward the follow request to the object_author's host
        if not actor.host.endswith('/api/'):
            actor.host = actor.host + '/api/'
        if not object_author.host.endswith('/api/'):
            object_author.host = object_author.host + '/api/'
        payload = {
            "type": "follow",
            "summary": f"{actor.displayName} wants to follow {object_author.displayName}",
            "actor": {
                "type": "author",
                "id": actor.id,
                "host": actor.host,
                "displayName": actor.displayName,
                "github": actor.github,
                "profileImage": actor.host + actor.profileImage,
                "page": actor.page
            },
            "object": {
                "type": "author",
                "id": object_author.id,
                "host": object_author.host,
                "displayName": object_author.displayName,
                "page": object_author.page,
                "github": object_author.github,
                "profileImage": object_author.profileImage
            }
        }

        # using http basic auth to authenticate with the node server using the node_author's username and password
        headers = {
                "Authorization": f"Basic {base64.b64encode(f'{node_author.displayName}:{node_author.first_name}'.encode()).decode()}",
                "Content-Type": "application/json",
                "host": node_author.host.split('//')[1],
                "X-original-host":  "https://social-distribution-crimson-464113e0f29c.herokuapp.com/api/"
            }
        print(node_author.host.split('//')[1])
        new = Following.follow(actor, object_author)
        if not new:
            return Response({"error": "Already following"}, status=400)
        follow = Following.objects.get(author1=actor, author2=object_author)
        follow.status = 'accepted'
        follow.save()
        
        print(object_author.id)
        response = requests.post(object_author.id + '/inbox', json=payload, headers=headers)
        print(response.status_code, response.text)

        return Response({"message": "Follow request forwarded"}, status=200)



@api_view(['GET'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_followers(request, author_serial):
    ''' example response
    {
    "type": "followers",      
    "followers":[
        {
            "type":"author",
            "id":"http://nodebbbb/api/authors/222",
            "host":"http://nodebbbb/api/",
            "displayName":"Lara Croft",
            "page":"http://nodebbbb/authors/222",
            "github": "http://github.com/laracroft",
            "profileImage": "http://nodebbbb/api/authors/222/posts/217/image"
        },
        {
            // Second follower author object
        },
        {
            // Third follower author object
        }
        ]
    }
    '''
    author = get_object_or_404(Author, author_serial=author_serial)
    followers = Following.get_followers(author)
    followers_data = {
        "type": "followers",
        "followers": []
    }
    for follower in followers:
        follower_dataa = {
            "type": "author",
            "id": follower.author1.id,
            "host": follower.author1.host,
            "displayName": follower.author1.displayName,
            "page": follower.author1.page,
            "github": follower.author1.github,
            "profileImage": follower.author1.host+ follower.author1.profileImage.url
        }
        followers_data["followers"].append(follower_dataa)
    return Response(followers_data, status=200)

@api_view(['GET'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_following(request, author_serial):
    ''' example response
    {
    "type": "following",      
    "following":[
        {
            "type":"author",
            "id":"http://nodebbbb/api/authors/222",
            "host":"http://nodebbbb/api/",
            "displayName":"Lara Croft",
            "page":"http://nodebbbb/authors/222",
            "github": "
            "profileImage": "http://nodebbbb/api/authors/222/posts/217/image"
        },
        {
            // Second following author object
        },
        {
            // Third following author object
        }
        ]
    }
    '''
    author = get_object_or_404(Author, author_serial=author_serial)
    following = Following.get_following(author)
    following_data = {
        "type": "following",
        "following": []
    }
    for follow in following:
        following_dataa = {
            "type": "author",
            "id": follow.author2.id,
            "host": follow.author2.host,
            "displayName": follow.author2.displayName,
            "page": follow.author2.page,
            "github": follow.author2.github,
            "profileImage": follow.author2.host+follow.author2.profileImage.url
        }
        following_data["following"].append(following_dataa)
    return Response(following_data, status=200)


