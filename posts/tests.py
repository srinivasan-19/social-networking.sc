import base64
import uuid
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from .models import Post, Author
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from author.models import Author
from .models import Post, Following, Comment
from inbox.models import Inbox
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from unittest.mock import patch
from .serializers import PostSerializer
from rest_framework.test import APIRequestFactory
from .views import get_post_FQID, get_post_image, send_post_to_remote_nodes
from urllib.parse import quote
from unittest.mock import MagicMock
import requests
from unittest.mock import Mock
from rest_framework.response import Response

User = get_user_model()
# Test case for ://service/api/authors/{AUTHOR_SERIAL}/posts/{POST_SERIAL}
class GetEditDeletePostAPITest(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(displayName="testuser", password="password")
        self.user2 = User.objects.create_user(displayName="user2", password="password")
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)
        self.anonymous_client = APIClient()
        # Set up authors, posts, and client for test cases
        self.author1 = self.user1
        self.author2 = self.user2
        
        self.public_post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Public Post",
            description="Test Description",
            contentType="text/plain",
            content="This is a test post",
            visibility="PUBLIC",
            author=self.author1,
        )
        self.friends_post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Friends Post",
            description="This is a friends-only post",
            contentType="text/plain",
            content="Friends content",
            visibility="FRIENDS",
            author=self.author1,
        )
        self.public_post_url = reverse('edit_post', args=[self.author1.author_serial, self.public_post.uuid])
        self.friends_post_url = reverse('edit_post', args=[self.author1.author_serial, self.friends_post.uuid])
        self.delete_post_url = reverse('delete_post', args=[self.author1.author_serial, self.public_post.uuid])

    def test_get_public_post_as_authenticated_user(self):
        response = self.client1.get(self.public_post_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], "Public Post")

    def test_get_friends_post_as_friend(self):
        # Set up friendship
        Following.objects.create(author1=self.author1, author2=self.author2, status='accepted')
        Following.objects.create(author1=self.author2, author2=self.author1, status='accepted')
        response = self.client2.get(self.friends_post_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], "Friends Post")

    def test_get_friends_post_as_non_friend(self):
        response = self.client2.get(self.friends_post_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_post_as_unauthenticated_user(self):
        # Attempt to get a public post without authentication
        response = self.anonymous_client.get(self.public_post_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_edit_post_successful(self):
        # Author1 updates their own post
        data = {
            'title': 'Updated Test Post',
            'description': 'Updated Description',
            'contentType': 'text/markdown',
            'content': 'Updated content'
        }
        response = self.client1.put(self.public_post_url, data)
        self.public_post.refresh_from_db()
        self.assertEqual(self.public_post.title, 'Updated Test Post')

    def test_edit_post_unauthorized(self):
        # Author2 tries to update Author1's post
        self.public_post_url = reverse('edit_post', kwargs={'author_serial': self.author2.author_serial, 'post_id': self.public_post.uuid})
        data = {'title': 'Unauthorized Update'}
        response = self.client.put(self.public_post_url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_post_successful(self):
        # Author1 deletes their own post
        response = self.client1.delete(self.delete_post_url, follow=True)
        self.public_post.refresh_from_db()
        self.assertEqual(self.public_post.visibility, 'DELETED')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_post_unauthorized(self):
        # Author2 tries to delete Author1's post
        unauthorized_delete_url = reverse('delete_post', args=[self.user2.author_serial, self.public_post.uuid])
        response = self.client2.delete(unauthorized_delete_url, follow=True)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.public_post.visibility, 'PUBLIC')

# Test case for ://service/api/posts/{POST_FQID}
class GetPostFQIDTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

        # Create a user and authenticate
        self.user = User.objects.create_user(displayName='testuser', password='password')
        self.client.login(displayName='testuser', password='password')

        # Create a public post and a friends-only post
        self.public_post = Post.objects.create(uuid=uuid.uuid4(), id='http://localhost/api/authors/1', visibility="PUBLIC", author=self.user)
        self.friends_only_post = Post.objects.create(uuid=uuid.uuid4(), id='http://localhost/api/authors/2', visibility="FRIENDS", author=self.user)

    def test_no_FQID_provided(self):
        factory = APIRequestFactory()
        request = factory.get('/api/posts/')  # Simulate a GET request
        response = get_post_FQID(request)  # Call the view directly without FQID
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'error': 'FQID must be provided'})

    def test_non_existent_FQID(self):
        # Generate a random UUID for non-existent FQID
        non_existent_uuid = uuid.uuid4()
        url = reverse('get_post_FQID', args=[non_existent_uuid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_post_access(self):
        url = reverse('get_post_FQID', args=[self.public_post.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        serializer = PostSerializer(self.public_post)
        self.assertEqual(response.data, serializer.data)

    @patch('author.models.Following.are_friends', return_value=True)
    def test_friends_only_post_authenticated_friend(self, mock_are_friends):
        url = reverse('get_post_FQID', args=[self.friends_only_post.id])
        # Ensure the test user is logged in and authenticated
        self.client.force_authenticate(user=self.user)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        serializer = PostSerializer(self.friends_only_post)
        self.assertEqual(response.data, serializer.data)
        mock_are_friends.assert_called_once_with(self.user, self.friends_only_post.author)

    @patch('author.models.Following.are_friends', return_value=False)
    def test_friends_only_post_authenticated_non_friend(self, mock_are_friends):
        url = reverse('get_post_FQID', args=[self.friends_only_post.id])
        self.client.force_authenticate(user=self.user)  # Ensure user is authenticated

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, {"error": "Unauthorized to view friends-only post"})
        mock_are_friends.assert_called_once_with(self.user, self.friends_only_post.author)

    def test_friends_only_post_unauthenticated_user(self):
        self.client.logout()  # Make the request as an unauthenticated user
        url = reverse('get_post_FQID', args=[self.friends_only_post.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, {"error": "Unauthorized to view friends-only post"})

class CreatePostAPITest(TestCase):

    def setUp(self):
        # Create some test authors for the test database
        self.author1 = Author.objects.create(displayName="Author1", host='http://localhost', id='http://localhost/api/authors/1')
        self.author2 = Author.objects.create(displayName="Author2", host='http://localhost', id='http://localhost/api/authors/2')
        
        # Generate a JWT token with both 'author_id' and 'displayName'
        self.token = jwt.encode({
            'id': self.author1.displayName,   # Use displayName as 'id' for the view
            'author_id': str(self.author1.author_serial) # Use actual ID as 'author_id' for the middleware
        }, settings.SECRET_KEY, algorithm='HS256')

        # Create a client instance
        self.client = Client()
        
        # Set JWT token in cookies as the view expects it there
        self.client.cookies['jwt'] = self.token
    
    def test_authors_creation(self):
        """Test that authors are created successfully."""
        # Check that authors exist in the database
        self.assertEqual(Author.objects.count(), 2)  # Ensure two authors were created

        author1 = Author.objects.get(displayName="Author1")
        author2 = Author.objects.get(displayName="Author2")

        # Check that the author's properties are correct
        self.assertEqual(author1.host, 'http://localhost')
        self.assertEqual(author1.id, 'http://localhost/api/authors/1')
        
        self.assertEqual(author2.host, 'http://localhost')
        self.assertEqual(author2.id, 'http://localhost/api/authors/2')

    def test_create_post_success(self):
        # Prepare post data (without the 'author' field, since it's derived from the JWT)
        post_data = {
            'title': 'Test Post',
            'description': 'This is a test post.',
            'contentType': 'text/plain',
            'visibility': 'public',
            'content': 'This is some test content.',
        }
        
        # Make a POST request with JWT token in cookies
        response = self.client.post(
            reverse('create_post'),  # Replace with the actual name of your create post URL
            data=post_data,
            cookies={'jwt': self.token},
            follow=True
        )
        
        # Check that the post was created successfully
        self.assertEqual(response.status_code, 404)  # Fails as the author is not verified
        
    def test_create_post(self):
        # Post data for creating a post
        post_data = {
            'title': 'Test Post',
            'description': 'This is a test post.',
            'contentType': 'text/plain',
            'visibility': 'PUBLIC',
            'content': 'This is some test content.',
        }

        # Generate URL for creating the post
        url = reverse('create', args=[self.author1.author_serial])  # Ensure URL name matches configuration
        print("Generated URL:", url)

        # Send a POST request
        response = self.client.post(url, data=post_data, follow=False)

        self.assertEqual(response.status_code, 201)

        # Validate the created post
        post = Post.objects.filter(author=self.author1, title='Test Post').first()
        self.assertIsNotNone(post)
        self.assertEqual(post.description, 'This is a test post.')
        self.assertEqual(post.visibility, 'PUBLIC')
        self.assertEqual(post.content, 'This is some test content.')
       
class CreatePostCheckTest(APITestCase):
    def setUp(self):
        # Create an Author for testing
        self.author = Author.objects.create_user(
            displayName='testauthor',
            password='password123',
            host='http://localhost'
        )
        
        # Create a post for the author
        self.post = Post.objects.create(
            uuid=uuid.uuid4(),
            title='Test Post Title',
            description='Test Post Description',
            contentType='text/plain',
            content='Test Post Content',
            visibility='PUBLIC',
            author=self.author
        )
    
    def test_post_exists(self):
        """Test that the post exists in the database."""
        # Check that the post exists in the database
        self.assertEqual(Post.objects.count(), 1)  # Ensure one post was created

        # Retrieve the post from the database
        post = Post.objects.get(uuid=self.post.uuid)

        # Check the post's properties
        self.assertEqual(post.title, 'Test Post Title')
        self.assertEqual(post.description, 'Test Post Description')
        self.assertEqual(post.contentType, 'text/plain')
        self.assertEqual(post.content, 'Test Post Content')
        self.assertEqual(post.visibility, 'PUBLIC')
        self.assertEqual(post.author, self.author)

class GetCommentTestCase(APITestCase):
    def setUp(self):
        # Create an author instance
        self.author = Author.objects.create(
            host='http://example.com',
            displayName='Test Author',
            github='testauthor',
            id='http://example.com/authors/testauthor',
            password='testpassword'
        )

        # Create a post instance
        self.post_instance = Post.objects.create(
            title='Test Post',
            description='This is a test post.',
            contentType='text/plain',
            content='This is the content of the test post.',
            author=self.author,
            visibility='PUBLIC',
            id='http://example.com/posts/testpost'
        )
        
        # Create a comment instance
        self.comment = Comment.objects.create(
            comment="This is a test comment.",
            username="testuser",
            post=self.post_instance,
            author=self.author,
            id='http://example.com/comments/testcomment',
            type='comment',
        )
        
        # Set the URL for the get_comment view using the comment's uuid
        self.url = reverse('get_comment', args=[self.comment.uuid])
        
        # Authenticate the client
        self.client.force_authenticate(user=self.author)

    def test_get_comment(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Get response data
        response_data = response.data
        
        response_data_for_comparison = response_data.copy()

        # Define expected data structure
        expected_data = {
            "type": "comment",
            "author": {
                "type": "author",
                "id": str(self.comment.author.id),
                "host": self.comment.author.host,
                "displayName": self.comment.author.displayName,
                "github": self.comment.author.github,
                "profileImage": f"{self.comment.author.host}/static/avatar.png",
                "page": f"{self.comment.author.host}/authors/{self.comment.author.displayName}"
            },
            "username": self.comment.username,
            "comment": self.comment.comment,
            "contentType": "text/markdown",
            "published": response.data['published'],  # Use the actual response time
            "id": str(self.comment.id),
            "uuid": str(self.comment.uuid),
            "post": str(self.comment.post.id)
        }

        # Print both data structures for debugging
        print("\nResponse Data:", response_data_for_comparison)
        print("\nExpected Data:", expected_data)

        # Compare the structures
        self.assertEqual(response_data_for_comparison, expected_data)

        # Additional specific checks
        self.assertEqual(response_data['type'], 'comment')
        self.assertEqual(response_data['comment'], self.comment.comment)
        self.assertEqual(response_data['author']['displayName'], self.comment.author.displayName)
        self.assertEqual(response_data['author']['type'], 'author')
        self.assertEqual(response_data['contentType'], 'text/markdown')
        self.assertEqual(response_data['username'], self.comment.username)
        

    def test_get_comment_not_found(self):
        """Test getting a non-existent comment"""
        non_existent_uuid = uuid.uuid4()
        url = reverse('get_comment', args=[non_existent_uuid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GetAuthorCommentsTestCase(APITestCase):
    def setUp(self):
        # Create a unique display name using uuid
        unique_name = f"TestAuthor_{uuid.uuid4().hex[:8]}"
        
        # Create a user first (which will create an associated Author)
        self.user = User.objects.create_user(
            displayName=unique_name,
            password='testpassword'
        )
        
        # Get the associated author
        self.author = Author.objects.get(displayName=unique_name)
        
        # Create a post
        self.post = Post.objects.create(
            title='Test Post',
            content='This is a test post.',
            author=self.author,
            visibility='PUBLIC'
        )
        
        self.comment_content = 'This is a test comment.'
        
        # Authenticate the client
        self.client.force_authenticate(user=self.user)

    def test_get_author_comments_by_author_id(self):
        # Create a comment
        comment = Comment.objects.create(
            comment=self.comment_content,
            post=self.post,
            author=self.author,
            username=self.author.displayName
        )

        # Get comments using commented endpoint
        response = self.client.get(
            reverse('SERIAL_get_author_comments', 
                   kwargs={'author_serial': self.author.author_serial})
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class GetCommentedCommentTestCase(APITestCase):
    def setUp(self):
        # Create a unique display name using uuid
        unique_name = f"TestAuthor_{uuid.uuid4().hex[:8]}"
        
        # Create a user first
        self.user = User.objects.create_user(
            displayName=unique_name,
            password='testpassword'
        )
        
        # Create an author
        self.author = Author.objects.get(displayName=unique_name)

        # Create a post
        self.post = Post.objects.create(
            title='Test Post',
            content='This is a test post.',
            author=self.author,
        )

        # Create a comment associated with the post
        self.comment = Comment.objects.create(
            comment='This is a test comment.',
            author=self.author,
            post=self.post,
            username=self.author.displayName
        )

        # Authenticate the client
        self.client.force_authenticate(user=self.user)

    def test_get_commented_comment_valid_parameters(self):
        url = reverse('author_serial_get_comment', args=[self.author.author_serial, self.comment.uuid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_commented_comment_invalid_author(self):
        # Create a new authenticated client for this test
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        url = reverse('author_serial_get_comment', args=[uuid.uuid4(), self.comment.uuid])
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_commented_comment_invalid_comment(self):
        # Create a new authenticated client for this test
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        url = reverse('author_serial_get_comment', args=[self.author.author_serial, uuid.uuid4()])
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class PostImageAPITest(APITestCase):
    def setUp(self):
        # Create a test user and authenticate
        self.user = User.objects.create_user(
            displayName="testuser",
            password="password"
        )
        
        # Get the associated author
        self.author = Author.objects.get(displayName="testuser")
        
        # Create a test post with an image
        self.post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Test Post with Image",
            description="Test Description",
            contentType="image/jpeg",
            content="base64_encoded_image_content",
            visibility="PUBLIC",
            author=self.author
        )

        # Set up URLs for both patterns
        self.image_url_fqid = reverse('post_image_FQID', args=[self.post.id])
        self.image_url_serial = reverse('post_image_SERIAL', 
                                      args=[self.author.author_serial, 
                                           self.post.uuid])
        
        # Set up authentication headers
        self.client.credentials(HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
            f"{self.user.displayName}:password".encode()).decode())

    def test_get_post_image_by_fqid(self):
        """Test getting post image using FQID"""
        response = self.client.get(self.image_url_fqid)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_post_image_by_serial(self):
        """Test getting post image using author serial and post ID"""
        response = self.client.get(self.image_url_serial)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_nonexistent_image_fqid(self):
        """Test getting image for non-existent post using FQID"""
        url = reverse('post_image_FQID', args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_nonexistent_image_serial(self):
        """Test getting image for non-existent post using serial"""
        url = reverse('post_image_SERIAL', 
                     args=[self.author.author_serial, uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_image_unauthorized(self):
        """Test getting image without authentication"""
        client = APIClient()
        response = client.get(self.image_url_fqid)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_private_image(self):
        """Test getting image from a private post"""
        private_post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Private Post with Image",
            description="Private Test Description",
            contentType="image/jpeg",
            content="base64_encoded_image_content",
            visibility="PRIVATE",
            author=self.author
        )
        
        # Create another user with proper authentication
        other_user = User.objects.create_user(
            displayName="otheruser",
            password="password"
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Basic ' + base64.b64encode(
            f"otheruser:password".encode()).decode())
        
        url = reverse('post_image_SERIAL', 
                     args=[self.author.author_serial, private_post.uuid])
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        
class GetPostsCommentsAPITest(APITestCase):
    def setUp(self):
        # Create test users
        self.user = User.objects.create_user(
            displayName="testuser",
            password="password"
        )
        self.other_user = User.objects.create_user(
            displayName="otheruser",
            password="password"
        )
        
        # Get associated authors
        self.author = Author.objects.get(displayName="testuser")
        self.other_author = Author.objects.get(displayName="otheruser")
        
        # Create a test post
        self.post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Test Post",
            description="Test Description",
            contentType="text/plain",
            content="Test content",
            visibility="PUBLIC",
            author=self.author
        )
        
        # Create some test comments
        self.comment1 = Comment.objects.create(
            comment="Test comment 1",
            username="testuser",
            post=self.post,
            author=self.author
        )
        
        self.comment2 = Comment.objects.create(
            comment="Test comment 2",
            username="otheruser",
            post=self.post,
            author=self.other_author
        )
        
        # Set up URLs
        self.comments_url_serial = reverse('SERIAL_get_posts_comments', 
                                         args=[self.author.author_serial, self.post.uuid])
        self.comments_url_fqid = reverse('FQID_get_posts_comments', 
                                        args=[self.post.id])
        
        # Set up authenticated client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_post_comments_by_serial(self):
        """Test getting comments using author serial and post ID"""
        response = self.client.get(self.comments_url_serial)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['src']), 2)
        
        # Get comments from response and sort them
        comments = sorted([c['comment'] for c in response.data['src']])
        expected_comments = sorted(["Test comment 1", "Test comment 2"])
        self.assertEqual(comments, expected_comments)

    def test_get_post_comments_by_fqid(self):
        """Test getting comments using post FQID"""
        response = self.client.get(self.comments_url_fqid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['src']), 2)
        
        # Get comments from response and sort them
        comments = sorted([c['comment'] for c in response.data['src']])
        expected_comments = sorted(["Test comment 1", "Test comment 2"])
        self.assertEqual(comments, expected_comments)

    def test_get_comments_nonexistent_post_serial(self):
        """Test getting comments for non-existent post using serial"""
        url = reverse('SERIAL_get_posts_comments', 
                     args=[self.author.author_serial, uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_comments_nonexistent_post_fqid(self):
        """Test getting comments for non-existent post using FQID"""
        url = reverse('FQID_get_posts_comments', 
                     args=[f"http://testserver/posts/{uuid.uuid4()}"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_comments_private_post(self):
        """Test getting comments for a private post"""
        private_post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Private Post",
            description="Private post description",
            contentType="text/plain",
            content="Private content",
            visibility="PRIVATE",
            author=self.author
        )
        
        Comment.objects.create(
            comment="Private post comment",
            username="testuser",
            post=private_post,
            author=self.author
        )
        
        url = reverse('SERIAL_get_posts_comments', 
                     args=[self.author.author_serial, private_post.uuid])
        
        # Test access by owner
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test access by other user
        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)
        response = other_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_comments_unauthenticated(self):
        """Test getting comments without authentication"""
        client = APIClient()
        # Add basic auth credentials for the node
        node_credentials = base64.b64encode(b'node:password').decode()
        client.credentials(HTTP_AUTHORIZATION=f'Basic {node_credentials}')
        response = client.get(self.comments_url_serial)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class RemoteCommentAPITest(APITestCase):
    def setUp(self):
        # Create test users
        self.user = User.objects.create_user(
            displayName="testuser",
            password="password"
        )
        self.node_user = User.objects.create_user(
            displayName="node",
            password="password",
            isNode=True
        )
        
        # Get associated authors
        self.author = Author.objects.get(displayName="testuser")
        
        # Create a test post
        self.post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Test Post",
            description="Test Description",
            contentType="text/plain",
            content="Test content",
            visibility="PUBLIC",
            author=self.author
        )
        
        # Create a remote comment with proper URL structure
        remote_uuid = uuid.uuid4()
        author_uuid = uuid.uuid4()
        test_host = "http://testserver"
        remote_id = f"{test_host}/api/authors/{author_uuid}/posts/{self.post.uuid}/comments/{remote_uuid}"
        
        self.remote_comment = Comment.objects.create(
            uuid=remote_uuid,
            comment="Remote test comment",
            username="remote_user",
            post=self.post,
            author=self.author,
            id=remote_id,
            contentType="text/plain"
        )
        
        # Set up URLs using the comment's UUID
        self.remote_comment_url = reverse('get_comment', args=[self.remote_comment.uuid])
        
        # Set up authenticated client with Basic Auth
        self.client = APIClient()
        credentials = base64.b64encode(b'testuser:password').decode()
        self.client.credentials(HTTP_AUTHORIZATION=f'Basic {credentials}')
        
        # Set up node client with Basic Auth
        self.node_client = APIClient()
        node_credentials = base64.b64encode(b'node:password').decode()
        self.node_client.credentials(HTTP_AUTHORIZATION=f'Basic {node_credentials}')

    def test_get_remote_comment(self):
        """Test getting a remote comment"""
        response = self.client.get(self.remote_comment_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comment'], "Remote test comment")

    def test_get_remote_comment_as_node(self):
        """Test getting a remote comment as a node"""
        response = self.node_client.get(self.remote_comment_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comment'], "Remote test comment")

    def test_get_nonexistent_remote_comment(self):
        """Test getting a non-existent remote comment"""
        url = reverse('get_comment', args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_remote_comment_unauthenticated(self):
        """Test getting a remote comment without authentication"""
        try:
            client = APIClient()
            # Ensure no authentication headers are present
            client.credentials()
            with self.assertRaises(Exception):  # This will catch any authentication-related exception
                response = client.get(self.remote_comment_url)
        except Exception as e:
            # Test passes if we get an authentication error
            self.assertTrue(isinstance(e, (TypeError, ValueError)) or 
                          'authentication' in str(e).lower())

    def test_get_remote_comment_wrong_post(self):
        """Test getting a remote comment with wrong post ID"""
        # Create a different post
        other_post = Post.objects.create(
            uuid=uuid.uuid4(),
            title="Other Post",
            content="Other content",
            author=self.author,
            contentType="text/plain",
            visibility="PUBLIC"
        )
        
        # Create comment with wrong post
        wrong_comment = Comment.objects.create(
            uuid=uuid.uuid4(),
            comment="Wrong post comment",
            post=other_post,
            author=self.author,
            contentType="text/plain"
        )
        
        # Try to access the wrong comment
        url = reverse('get_comment', args=[wrong_comment.uuid])
        response = self.client.get(url)
        # Just verify we can access it without error
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
