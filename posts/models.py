from datetime import datetime
from django.db import models
from author.models import Author, Following
from django.utils import timezone
import uuid
from django.contrib.contenttypes.fields import GenericRelation

VISIBILITY_CHOICES = [
    ('PUBLIC', 'Public'),
    ('FRIENDS', 'Friends'),
    ('UNLISTED', 'Unlisted'),
    ('DELETED', 'Deleted')
]

CONTENT_TYPE_CHOICES = [
    ('text/markdown', 'Markdown'),
    ('text/plain', 'Plain Text'),
    ('application/base64', 'Base64 Image'),
    ('image/png;base64', 'PNG Image'),
    ('image/jpeg;base64', 'JPEG Image')
]


class Like(models.Model):
    type = models.CharField(max_length=255, default="like")
    username = models.CharField(max_length=255, default="1")  # Store the display name instead of Author object
    uuid = models.UUIDField( default=uuid.uuid4, editable=False)
    published = models.DateTimeField(default=timezone.now)
    author = models.ForeignKey(Author, related_name='likes', on_delete=models.CASCADE)
    id = models.CharField(max_length=1000, primary_key=True, unique=True)
    post = models.ForeignKey('Post', related_name='likes', on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey('Comment', related_name='likes', on_delete=models.CASCADE, null=True, blank=True)
    object = models.CharField(max_length=255, blank=True, null=True)  # Adding 'object' field as a CharField

    def __str__(self):
        # Adjust string representation based on whether it's a post or comment like
        if self.post:
            return f"{self.username} liked the post '{self.post.title}'"
        elif self.comment:
            return f"{self.username} liked a comment by {self.comment.author.username}"
        return f"{self.username} liked something"

    def save(self, *args, **kwargs):
        """
        Ensure that only one of post or comment is set.
        """
        host = kwargs.get('request_host', 'social-distribution-crimson-464113e0f29c.herokuapp.com')
        author_id = self.author.author_serial  # Ensure that author id is correctly set
        self.id = f"http://{host}/api/authors/{author_id}/liked/{self.uuid}"
        if self.post:
            self.object = str(self.post.id)
        elif self.comment:
            self.object = str(self.comment.id)
        else:
            self.object = None  # Set to None if neither post nor comment is set
        if self.post and self.comment:
            raise ValueError("A Like object cannot be associated with both a post and a comment.")
        if not self.post and not self.comment:
            raise ValueError("A Like object must be associated with either a post or a comment.")
        super().save(*args, **kwargs)


class Likes(models.Model):
    type = models.CharField(max_length=20, default="likes")
    page = models.URLField()  # URL of the page
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page_number = models.IntegerField(default=1)
    size = models.IntegerField(default=50)  # Size of the page (number of likes per page)
    count = models.IntegerField(default=0)  # Total number of likes
    src = models.ManyToManyField(Like, related_name='like_collections')  # Links to individual Like objects
    
    def __str__(self):
        return f"Likes Collection for {self.id}"
    
    def add_like(self, like):
        """
        Add a like to the src field and increment the count.
        """
        self.src.add(like)
        self.count = self.src.count()
        self.save()

    def get_likes_sorted(self):
        """
        Return the likes sorted by newest (first) to oldest (last).
        """
        return self.src.order_by('-published')

# Create your models here.
class Post(models.Model):
    id = models.CharField(max_length=1000, primary_key=True, unique=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20)
    title = models.CharField(max_length=100)
    page = models.URLField()
    description = models.CharField(max_length=200)
    contentType = models.CharField(max_length=100, choices=CONTENT_TYPE_CHOICES)
    content = models.TextField()
    author = models.ForeignKey(Author, related_name='posts', on_delete=models.CASCADE)
    published = models.DateTimeField(auto_now_add=True)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES)
    likes_collection = models.OneToOneField(Likes, related_name='post', on_delete=models.CASCADE, null=True, blank=True)
    likes = GenericRelation('Like')

    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Ensure FQID is set on creation only
        if not self.id:
            author_serial = self.author.author_serial # Ensure that author id is correctly set
            self.id = f"{self.author.host}/api/authors/{author_serial}/posts/{self.uuid}"
        if not self.page:
            author_serial = self.author.author_serial  # Ensure that author id is correctly set
            self.page = f"{self.author.host}authors/{author_serial}/posts/{self.uuid}"
        
        super().save(*args, **kwargs)
    
    def is_visible_to(self, user):
        """Determine if the current post is visible to the specified user."""
        # Deleted posts should not be visible to anyone except admins
        if self.visibility == 'DELETED':
            return False

        # Public posts are visible to everyone
        if self.visibility == 'PUBLIC':
            return True

        # Unlisted posts are visible only to logged-in users with a link
        if self.visibility == 'UNLISTED':
            return Following.is_following(user, self.author) or user == self.author

        # Friends-only posts are visible to friends (mutual followers)
        if self.visibility == 'FRIENDS':
            return Following.are_friends(self.author, user) or user == self.author

        # By default, the post is not visible
        return False

class Comment(models.Model):
    type = models.CharField(max_length=20, default='comment')
    author = models.ForeignKey(Author, related_name='comments', on_delete=models.CASCADE)
    username = models.CharField(max_length=32) 
    comment =  models.TextField()
    contentType = models.CharField(max_length=32, default="text/markdown")
    published = models.DateTimeField("date created", default=timezone.now) 
    id = models.CharField(primary_key=True, max_length=1000, unique=True)  # FQID
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)   # SERIAL
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE) # all comments belong to a post
    likes_collection = models.OneToOneField(Likes, related_name='comment', on_delete=models.CASCADE, null=True, blank=True)
    likes = GenericRelation('Like')

    def save(self, *args, **kwargs):
        """Override the save method to set the id field before saving."""
        if not self.id:  # Only set if id is not already set
            if hasattr(self, '_host'):
                self.id = f"http://{self._host}/api/comments/{self.uuid}"
            else:
                self.id = f"http://localhost/api/comments/{self.uuid}"  # Default to 'localhost'

        if not self.likes_collection:
            likes = Likes.objects.create()
            self.likes_collection = likes
        super().save(*args, **kwargs)


class githubPostIds(models.Model):
    '''
    This model is used to store the post id of the posts that are created in github
    '''
    id = models.IntegerField(primary_key=True)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    

    
