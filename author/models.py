from django.db import models
import uuid
from django.contrib.auth.models import AbstractUser
from .managers import CustomUserManager
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest  # Import HttpRequest to simulate request.get_host()
from django.utils import timezone
class Author(AbstractUser):
    '''
    Custom User model to represent an author in the system
    The model extends the AbstractUser model and overrides the username field with displayName
    '''
    # set type to author and make it read only
    TYPE_CHOICES = [("author", "Author"), ("node", "Node")]
    
    # New field to differentiate between author and node
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="author")
    author_serial = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id = models.CharField(max_length= 1000, unique=True, null=True)
    host = models.CharField(max_length=255, null=False)
    displayName = models.CharField(_("displayName"),max_length=100, unique=True)
    github = models.CharField(max_length=255, blank=True, null=True)
    profileImage = models.URLField(blank=True, null=True) 
    page = models.CharField( max_length=1000,blank=True, null=True)
    isVerified = models.BooleanField(default=False)
    isNode = models.BooleanField(default=False)
    username = None


    USERNAME_FIELD = 'displayName'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.displayName

    def save(self, *args, **kwargs):
        '''
        Override the save method to set the host field if not already set
        '''
        Default_profile_image = '/static/avatar.png'
        request = kwargs.pop('request', None)
    
        if not self.host and request:
            scheme = "https" if 'heroku' in request.get_host() else request.scheme
            host = request.get_host()
            self.host = f"{scheme}://{host}"
        elif not self.host:
            self.host = "http://localhost"

        if not self.id:
            self.id = f"{self.host}/api/authors/{self.author_serial}"

        if not self.profileImage:
            self.profileImage = f"{self.host}{Default_profile_image}"  # Construct the full URL

        if not self.page:
            self.page = f"{self.host}/authors/{self.displayName}"

        super().save(*args, **kwargs)
        
    def is_friend(self, other_author):
        """ Check if there is a mutual following relationship with another author, indicating friendship. """
        return Following.are_friends(self, other_author)

# New FollowRequest Model
class FollowRequest(models.Model):
    actor = models.ForeignKey(Author, related_name='follow_requests_sent', on_delete=models.CASCADE)
    object_author = models.ForeignKey(Author, related_name='follow_requests_received', on_delete=models.CASCADE)
    summary = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=[('pending', 'Pending'), ('accepted', 'Accepted')], default='pending')

    def __str__(self):
        return f"{self.actor.displayName} wants to follow {self.object_author.displayName}"
    
class Following(models.Model):
    '''Model to store following relationship between authors. author1 is following author2
    this table represents following which is a many to many relationship btw author (author1, author2)
    Exist (a,b) a is following b AND Exist(b,a) b is following a --> friend;  
    Exist(a,b) AND not exist (b,a) --> a is follower of b or b is followed by a
    This is all we need to fetch the relation between authors'''

    type = "follow"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author1 = models.ForeignKey(Author, related_name='author', on_delete=models.CASCADE) # actor
    author2 = models.ForeignKey(Author, related_name='following', on_delete=models.CASCADE) # object
    status = models.CharField(max_length=50, choices=[('pending', 'Pending'), ('accepted', 'Accepted')], default='pending')
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.author1.displayName} is following {self.author2.displayName}"

    @staticmethod
    def is_following(author1, author2):
        """Check if author1 is following author2."""
        return Following.objects.filter(author1=author1, author2=author2, status='accepted').exists()

    @staticmethod
    def are_friends(author1, author2):
        """Check if both authors are following each other (mutual following)."""
        return (Following.objects.filter(author1=author1, author2=author2, status="accepted").exists() and
            Following.objects.filter(author1=author2, author2=author1, status="accepted").exists())
        
    @staticmethod
    def follow(author1, author2):
        """Follow an author."""
        new = None  # if new following relationship is created return it else return None
        if not Following.objects.filter(author1=author1, author2=author2).exists():
            new = Following.objects.create(author1=author1, author2=author2)
        return new
    
    @staticmethod
    def unfollow(author1, author2):
        """Unfollow an author and potentially unfriend."""
        Following.objects.filter(author1=author1, author2=author2).delete()
    
    @staticmethod
    def get_followers(author):
        """Get all authors following an author."""
        return Following.objects.filter(author2=author, status='accepted')
    
    @staticmethod
    def get_following(author):
        """Get all authors an author is following."""
        return Following.objects.filter(author1=author, status='accepted')
