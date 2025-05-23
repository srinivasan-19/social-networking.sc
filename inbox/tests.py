from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import Inbox, Post
from author.models import Author, Following
from posts.models import Like, Comment
from unittest.mock import patch, PropertyMock
from rest_framework.response import Response

import jwt
from django.conf import settings
from datetime import datetime, timedelta
import uuid

class InboxTests(APITestCase):
    def setUp(self):
        # Create an author and set up login credentials
        self.author_password = "test_password"
        self.base_host = "http://example.com"
        
        self.author = Author.objects.create_user(
            displayName="test_author",
            password=self.author_password,
            host=self.base_host,
            isVerified=True,
            profileImage="default.png"
        )
        self.author.save()

        # Create a second author for interactions
        self.other_author = Author.objects.create_user(
            displayName="other_author",
            password="other_password",
            host=self.base_host,
            isVerified=True,
            profileImage="default.png"
        )
        self.other_author.save()

        # Define URLs with correct format
        self.login_url = reverse('login')
        self.inbox_url = reverse('inbox')
        self.inbox_api_url = reverse('follow_request', kwargs={'object_author_serial': self.author.author_serial})
        
        # Make sure this matches the URL pattern in urls.py
        self.follow_request_url = reverse('follow_request_response', kwargs={
            'author_serial': self.author.author_serial,
            'foreign_author_fqid': f"{self.base_host}/api/authors/{self.other_author.author_serial}"
        })
        
        self.get_followers_url = reverse('get_followers', kwargs={'author_serial': self.author.author_serial})
        self.get_following_url = reverse('get_following', kwargs={'author_serial': self.author.author_serial})
        self.forward_follow_request_url = reverse('forward_follow_request')

    def authenticate(self):
        # Perform login and store the JWT token in cookies
        response = self.client.post(self.login_url, data={'displayName': self.author.displayName, 'password': self.author_password})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Retrieve the JWT token from the login response cookie
        token = response.cookies.get(settings.JWT_AUTH_COOKIE).value
        self.client.cookies[settings.JWT_AUTH_COOKIE] = token

    def test_get_inbox_unauthenticated(self):
        response = self.client.get(self.inbox_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_inbox_authenticated(self):
        self.authenticate()
        response = self.client.get(self.inbox_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_send_follow_request(self):
        self.authenticate()
        follow_data = {
            "type": "follow",
            "actor": {
                "id": str(self.author.id),
                "host": "http://example.com/",
                "displayName": "test_author"
            },
            "object": {
                "id": str(self.other_author.id),
                "host": "http://example.com/",
                "displayName": "other_author"
            }
        }
        response = self.client.post(self.inbox_api_url, data=follow_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['requestStatus'], 'pending')
        self.assertEqual(Following.objects.filter(author1=self.author, author2=self.other_author).count(), 1)

    def test_accept_follow_request(self):
        self.authenticate()
        Following.objects.create(author1=self.other_author, author2=self.author, status='pending')
        response = self.client.put(self.follow_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        follow_request = Following.objects.get(author1=self.other_author, author2=self.author)
        self.assertEqual(follow_request.status, 'accepted')


    def test_get_followers(self):
        """Test getting followers list"""
        # Create a follower
        Following.objects.create(
            author1=self.other_author,
            author2=self.author,
            status='accepted'
        )
        
        self.authenticate()
        
        # Mock the profileImage property to return a FileField-like object
        class MockFile:
            url = 'default.png'
        
        with patch.object(Author, 'profileImage', new_callable=PropertyMock) as mock_profile:
            mock_file = MockFile()
            mock_profile.return_value = mock_file
            
            response = self.client.get(self.get_followers_url)
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['type'], 'followers')
            self.assertEqual(len(response.data['followers']), 1)
            
            follower = response.data['followers'][0]
            self.assertEqual(follower['displayName'], self.other_author.displayName)
            self.assertEqual(follower['host'], self.other_author.host)
            
            # Check that the ID matches the expected format
            expected_id = f"{self.other_author.host}/api/authors/{self.other_author.author_serial}"
            self.assertEqual(follower['id'], expected_id)
            
            # Check that profileImage exists
            self.assertIn('profileImage', follower)


    def test_get_following(self):
        """Test getting following list"""
        Following.objects.create(
            author1=self.author,
            author2=self.other_author,
            status='accepted'
        )
        
        self.authenticate()
        
        # Mock the profileImage property to return a FileField-like object
        class MockFile:
            url = 'default.png'
        
        with patch.object(Author, 'profileImage', new_callable=PropertyMock) as mock_profile:
            mock_file = MockFile()
            mock_profile.return_value = mock_file
            
            response = self.client.get(self.get_following_url)
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['type'], 'following')
            self.assertEqual(len(response.data['following']), 1)
            
            following = response.data['following'][0]
            self.assertEqual(following['displayName'], self.other_author.displayName)
            self.assertEqual(following['host'], self.other_author.host)
            
            # Check that profileImage exists
            self.assertIn('profileImage', following)


    def test_get_followers_not_found(self):
        """Test getting followers for non-existent author"""
        self.authenticate()
        non_existent_id = uuid.uuid4()
        url = reverse('get_followers', kwargs={'author_serial': non_existent_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_following_not_found(self):
        """Test getting following for non-existent author"""
        self.authenticate()
        non_existent_id = uuid.uuid4()
        url = reverse('get_following', kwargs={'author_serial': non_existent_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_handle_follow_request_not_found(self):
        """Test handling follow request for non-existent author"""
        self.authenticate()
        non_existent_id = uuid.uuid4()
        url = reverse('follow_request_response', 
                     kwargs={
                         'author_serial': non_existent_id,
                         'foreign_author_fqid': str(self.other_author.id)
                     })
        response = self.client.put(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inbox_api_unauthorized(self):
        """Test inbox API without authentication"""
        follow_data = {
            "type": "follow",
            "actor": {
                "id": f"http://example.com/api/authors/{self.author.author_serial}",
                "host": "http://example.com/",
                "displayName": "test_author"
            },
            "object": {
                "id": f"http://example.com/api/authors/{self.other_author.author_serial}",
                "host": "http://example.com/",
                "displayName": "other_author"
            }
        }
        
        # Create a client with raise_request_exception=False to handle authentication errors
        self.client = APIClient(raise_request_exception=False)
        
        # Clear any existing authentication
        self.client.credentials()  # Remove any existing credentials
        self.client.cookies.clear()  # Clear any existing cookies
        
        # Add invalid authentication header to trigger 401
        self.client.credentials(HTTP_AUTHORIZATION='Basic invalid_credentials')
        
        # Make the request without valid authentication
        response = self.client.post(self.inbox_api_url, data=follow_data, format='json')
        
        # Check that the response indicates unauthorized access
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
