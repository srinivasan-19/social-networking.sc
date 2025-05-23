from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import AuthorViewSet, profile_view, author_about, loginPage, user_settings, follow_author, followers_list, following_list, unfollow_author
from posts.views import PostViewSet
from django.contrib.auth import views as auth_views
from . import views

router = DefaultRouter()
router.register(r'authors', AuthorViewSet, basename='author')  # Registers /authors/ endpoint
router.register(r'posts', PostViewSet, basename='post')  # Registers /posts/ endpoint

urlpatterns = [
    # API and authentication routes
    path('api/', include(router.urls)),  
    path('login/', loginPage, name='loginPage'),
    path('send_req/', AuthorViewSet.as_view({'post': 'send_follow_request'}), name='send-follow-request'),
    
    # Follow management endpoints
    path('authors/<path:author_id>/follow/', follow_author, name='follow-author'),
    path('authors/<path:author_id>/unfollow/', unfollow_author, name='unfollow-author'),
    re_path(
        r'^(?P<author_serial>[0-9a-f-]+)/followers/(?P<foreign_author_id>.+)/$',
        views.manage_follower,
        name='manage_follower'
    ),
    
    # Author specific routes - most specific first
    path('<path:author_id>/followers/', followers_list, name='followers_list'),
    path('<path:author_id>/following/', following_list, name='following_list'),
    path('<path:author_id>/about/', author_about, name='author-about'),
    path('<path:author_id>/settings', user_settings, name='user-settings'),
    
    # Most general route should be last
    path('<path:author_id>/', profile_view, name='author_profile'),
]
