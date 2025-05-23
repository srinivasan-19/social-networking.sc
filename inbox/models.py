from django.db import models
from author.models import Author
from posts.models import Post
import uuid

# Create your models here.
INBOX_ENTRY_TYPE_CHOICES = [
    ('post', 'Post'),
    ('shared_post', 'Shared Post'),
    ('follow', 'Follow Request'),
    ('like', 'Like'),
    ('comment', 'Comment'),
]

class Inbox(models.Model):
    ''' create user inbox entry'''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receiver = models.ForeignKey(Author, related_name='inboxOwner', on_delete=models.CASCADE, null=True) # author who receives the notification
    type = models.CharField(max_length=11, choices=INBOX_ENTRY_TYPE_CHOICES)  # inbox entery type
    FQIDorId = models.CharField(max_length= 1000, unique=True, null=True) # FQIDorId of the target object can be following, post, comment, like
    received_at = models.DateTimeField() # time when the notification is received
    def __str__(self):
        return f'{self.receiver} {self.type} {self.FQIDorId}'

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    author = models.ForeignKey(Author, related_name='inbox', on_delete=models.CASCADE)
    type = models.CharField(max_length=11, choices=INBOX_ENTRY_TYPE_CHOICES)
    post = models.ForeignKey(Post, null=True, blank=True, on_delete=models.SET_NULL)
    # follow_request = models.ForeignKey(Authors, null=True, blank=True, on_delete=models.SET_NULL)
    received_at = models.DateTimeField()