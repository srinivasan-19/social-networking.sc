from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views


# Create a router and register your viewsets with it
router = DefaultRouter()
router.register(r'posts', views.PostViewSet, basename='posts')  # Ensure this is included
router.register(r'comments', views.CommentViewSet, basename='comments')
router.register(r'likes', views.LikeViewSet, basename='likes')

urlpatterns = [
    path("api/", include(router.urls)),
    path("", views.post, name="create_post"),
    path('<path:fqid>/editpost/', views.view_edit_post, name='view_edit_post'),
    path("<path:fqid>/viewPost/", views.view_post, name="viewPost"), # path to the specific post

    path("<uuid:id>/viewPost/repost_post/", views.repost_post, name="repost_post"),  # URL for repost functionality
    path("<uuid:id>/viewPost/repost_link/", views.repost_link, name="repost_link"),  # URL for repost functionality

    # API paths for creating comments and likes
    path("api/<uuid:post_uuid>/comment/", views.create_comment, name="create_comment"),  # API for creating comments
    path("api/<uuid:author_serial>/like/", views.api_create_like, name="api_create_like")
]