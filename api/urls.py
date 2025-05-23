from django.urls import path
from posts.views import forward_comment, get_author_comments, get_comment, get_commented_comment, get_edit_delete_post, get_posts_comments,get_posts_create_post,get_post_image
from posts.views import get_edit_delete_post,get_posts_create_post,get_post_image, github_post, api_create_like, api_view_postLikes, api_view_Likes, get_post_FQID, api_view_Likes_comments
from author.views import api_list_authors, api_add_author, api_author_detail, login, signup, get_author_from_cookie, logout, get_likes_by_author, get_single_like, api_get_like, serve_profile_image, upload_profile_image
from inbox.views import get_followers, get_following
from inbox.views import handle_follow_request_response, inboxApi, forward_follow_request, forward_like_request
from .views import nodeSignup, get_nodes

urlpatterns = [
    path('signup', signup, name='signup'),
    path('login', login, name='login'),
    path('author', get_author_from_cookie, name='get_author_from_cookie'),
    path('logout', logout, name='logout'),
    path("nodeSignup", nodeSignup, name="remoteNodeSignup"),
    path("nodes", get_nodes, name="get_nodes"),

    path("authors/<uuid:object_author_serial>/inbox", inboxApi, name="follow_request"), # sender of the follow request
    path("authors/<uuid:author_serial>/followers" , get_followers, name="get_followers"), # get followers of an author
    path("authors/<uuid:author_serial>/following" , get_following, name="get_following"), # get following of an author
    path("authors/<uuid:author_serial>/followers/<path:foreign_author_fqid>", handle_follow_request_response, name="follow_request_response"), # receiver of the follow request, replies to the follow request
    path("forwardFollowRequest", forward_follow_request, name="forward_follow_request"), # forward follow request to remote node

    # Image Posts API
    path('posts/<path:FQID>/image', get_post_image, name='post_image_FQID'),
    path('authors/<uuid:author_serial>/posts/<uuid:post_id>/image', get_post_image, name='post_image_SERIAL'),

    # Comments API
    path('comment/<uuid:comment_id>', get_comment, name='get_comment'),
    path('authors/<uuid:author_serial>/posts/<uuid:post_id>/comments', get_posts_comments, name='SERIAL_get_posts_comments'),
    path('posts/<path:post_FQID>/comments', get_posts_comments, name='FQID_get_posts_comments'),
    path('authors/<uuid:author_serial>/posts/<uuid:post_serial>/comment/<path:remote_comment_FQID>', get_comment, name='get_comment_remote_FQID'),
    path('post/<path:post_FQID>/viewPost/forward', forward_comment, name="forward_comment"),

    # Commented API
    path('authors/<uuid:author_serial>/commented', get_author_comments, name='SERIAL_get_author_comments'),
    path('authors/<path:FQID>/commented', get_author_comments, name='FQID_get_author_comments'),
    path('authors/<uuid:author_serial>/commented/<uuid:comment_id>', get_commented_comment, name='author_serial_get_comment'),
    path('commented/<path:FQID>', get_commented_comment, name='author_FQID_get_comment'),

    path('authors/<uuid:author_serial>/posts/<uuid:post_id>', get_edit_delete_post, name='edit_post'), # API for editing post
    path('authors/<uuid:author_serial>/posts/', get_posts_create_post, name='get_posts'),
    path("authors/<uuid:author_serial>/posts/", get_posts_create_post, name="create"),
    path('authors/<uuid:author_serial>/posts/<uuid:post_id>', get_edit_delete_post, name='delete_post'),
    path('posts/<path:FQID>', get_post_FQID, name='get_post_FQID'),
    path('authors/<uuid:author_serial>/gitPost/', github_post, name='github_post'),

    # Author API endpoints
    path('authors/', api_list_authors, name='api_list_authors'), # list all authors (local and remote)
    path('authors/add/', api_add_author, name='api_add_author'),  
    path('authors/<uuid:author_serial>/', api_author_detail, name='api_author_detail'),
    path('authors/<uuid:author_serial>/liked', get_likes_by_author, name='get_likes_by_author'),
    path("authors/<uuid:author_serial>/liked/<uuid:like_serial>",get_single_like,name="single_like"),
    path("liked/<uuid:like_fqid>",api_get_like,name="get_like"),
    path('authors/<uuid:author_serial>/image', serve_profile_image, name='serve_profile_image'),
    path('upload-profile-image/', upload_profile_image, name='upload_profile_image'),

    
    # Post API endpoints
    #path("authors/<uuid:author_serial>/inbox", api_create_like, name="api_create_like"),  # API for liking a post
    path("authors/<uuid:author_serial>/posts/<uuid:post_id>/likes", api_view_postLikes, name="api_likes"), # path to posts view likes
    path("posts/<uuid:post_id>/likes",api_view_Likes,name="api_view_Likes"),
    path("authors/<uuid:author_serial>/posts/<uuid:post_id>/comments/<path:comment_id>/likes",api_view_Likes_comments,name="api_likes_comments"),
    path("forward_like_request", forward_like_request, name="forward_like_request"), # forward follow request to remote node, name="forward_follow_request"), # forward follow request to remote node
    
]