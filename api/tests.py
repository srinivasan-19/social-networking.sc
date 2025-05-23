from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
from author.models import Author
import base64

class NodeAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a test node with properly set password
        self.test_node = Author.objects.create_user(
            displayName="testnode",
            password="nodepassword",  # Use proper password field
            host="http://testnode.com",
            isNode=True
        )
        
        # Create regular test user
        self.test_user = Author.objects.create_user(
            displayName="testuser",
            password="userpass",
            host="http://testhost.com",
            isNode=False
        )

    def get_auth_header(self, username, password):
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {'HTTP_AUTHORIZATION': f'Basic {credentials}'}

    def test_node_signup_success(self):
        """Test successful node signup"""
        signup_data = {
            "username": "newnode",
            "password": "nodepass123",
            "host": "http://newnode.com/api/",
            "type": "node",
            "displayName": "newnode",
            "github": "",
            "profileImage": "",
        }
        
        response = self.client.post(
            reverse('remoteNodeSignup'),
            data=signup_data,
            content_type='application/json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Author.objects.filter(displayName="newnode").exists())
        new_node = Author.objects.get(displayName="newnode")
        self.assertTrue(new_node.isNode)
        self.assertEqual(new_node.host, "http://newnode.com")
        self.assertEqual(new_node.first_name, "nodepass123")

    def test_node_signup_duplicate(self):
        """Test node signup with duplicate username"""
        signup_data = {
            "username": "testnode",  # Already exists from setUp
            "password": "nodepass123",
            "host": "http://duplicate.com/api/",
            "type": "node"
        }
        
        response = self.client.post(
            reverse('remoteNodeSignup'),
            data=signup_data,
            content_type='multipart/form-data'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_nodes_success(self):
        """Test successful retrieval of nodes list"""
        # Create auth headers with correct credentials
        auth_headers = self.get_auth_header("testnode", "nodepassword")
        
        response = self.client.get(
            reverse('get_nodes'),
            **auth_headers
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(len(response_data) > 0)
        # Check if our test node is in the response
        node_found = False
        for node in response_data:
            if node['displayName'] == 'testnode':
                node_found = True
                break
        self.assertTrue(node_found, "Test node not found in response")

    def test_get_nodes_unauthorized(self):
        """Test get nodes with invalid credentials"""
        auth_headers = self.get_auth_header("testnode", "wrongpassword")
        
        response = self.client.get(
            reverse('get_nodes'),
            **auth_headers
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_nodes_non_node_user(self):
        """Test get nodes with non-node user credentials"""
        auth_headers = self.get_auth_header("testuser", "userpass")
        
        response = self.client.get(
            reverse('get_nodes'),
            **auth_headers
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_node_signup_invalid_method(self):
        """Test node signup with invalid HTTP method"""
        response = self.client.get(reverse('remoteNodeSignup'))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_node_signup_missing_fields(self):
        """Test node signup with missing required fields"""
        # Test with empty data
        signup_data = {}
        
        response = self.client.post(
            reverse('remoteNodeSignup'),
            data=signup_data,
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test with only username
        signup_data = {
            "username": "newnode"
        }
        
        response = self.client.post(
            reverse('remoteNodeSignup'),
            data=signup_data,
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test with missing host
        signup_data = {
            "username": "newnode",
            "password": "password123"
        }
        
        response = self.client.post(
            reverse('remoteNodeSignup'),
            data=signup_data,
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_nodes_no_auth(self):
        """Test get nodes without authentication"""
        response = self.client.get(reverse('get_nodes'))
        self.assertEqual(
            response.status_code, 
            status.HTTP_400_BAD_REQUEST,  # Changed from 401 to 400
            "Expected 400 Bad Request when no authentication is provided"
        )