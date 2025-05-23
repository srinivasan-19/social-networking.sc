from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from posts.models import Post
from author.models import Following
from django.utils.safestring import mark_safe
import json
def home_page(request):
    '''
    View for the home page
    '''
    # Redirect to login if the user is not authenticated
    if not request.user.is_authenticated:
        return redirect('loginPage')
    # Access JWT payload if needed (optional)
    jwt_payload = request.jwt_payload  # Optional
    if jwt_payload:
        author_id = jwt_payload.get('author_id')

    # Fetch all posts, but we will only include posts the user is allowed to see
    all_posts = Post.objects.all().order_by('-published')
    following_list = []

    for post in all_posts:
        # Check if the post is visible to the current user using is_visible_to method
        if post.is_visible_to(request.user):
            is_following = Following.is_following(request.user, post.author) if request.user.is_authenticated else False

            # Append post follow status to the list if visible
            following_list.append(is_following)

    # Render the home page with follow status
    return render(request, 'home/home_page.html', {
        'following_list': mark_safe(json.dumps(following_list)),
    })