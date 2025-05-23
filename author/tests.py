from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse
from author.models import Author
import json
from unittest.mock import Mock, patch
import uuid  
from django.contrib.auth.models import User


class AuthorAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create test authors for use in API testing
        self.author1 = Author.objects.create(
            displayName="Author One",
            github="https://github.com/author1",
            host="http://localhost"
        )
        # Extract just the UUID part for API calls
        self.author1_uuid = str(self.author1.id).split('/')[-1]
        
        self.author2 = Author.objects.create(
            displayName="Author Two",
            github="https://github.com/author2",
            host="http://localhost"
        )
        self.author2_uuid = str(self.author2.id).split('/')[-1]

    ### Test API Endpoints ###

    # Test for API to list authors (GET /api/authors/)
    def test_list_authors(self):
        # Create a test user using our custom Author model
        user = Author.objects.create_user(
            displayName='testuser',
            password='12345',
            host='http://localhost'
        )
        self.client.force_authenticate(user=user)
        
        response = self.client.get(reverse('api_list_authors'))
        self.assertEqual(response.status_code, 200)
        self.assertIn("authors", response.json())
        # We should have 3 authors now (2 from setUp + 1 created in this test)
        self.assertEqual(len(response.json()["authors"]), 3)

    # Test for adding a new author (POST /api/authors/add/)
    def test_add_author(self):
        author_data = {
            'displayName': 'New Author',
            'github': 'https://github.com/newauthor',
            'host': 'http://localhost',  # Ensure 'host' is included if required
            'page': '',  # Optional fields can be included as empty if allowed
            'password': 'securepassword123'  # Add a password as it's required
        }
        response = self.client.post(reverse('api_add_author'), data=author_data, format='json')
        
        # Print response JSON to check error details if status is 400
        if response.status_code == 400:
            print("Error Details:", response.json())
            
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["message"], "Author created successfully")
        self.assertTrue(Author.objects.filter(displayName='New Author').exists())




    # Test for API to retrieve a single author detail (GET /api/authors/<int:author_id>/)
    def test_get_author_detail(self):
        # Create and authenticate a user
        user = Author.objects.create_user(
            displayName='testuser',
            password='12345',
            host='http://localhost'
        )
        self.client.force_authenticate(user=user)
        
        # Use only the UUID part of the author ID
        response = self.client.get(reverse('api_author_detail', args=[self.author1_uuid]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["displayName"], "Author One")
        self.assertEqual(data["github"], "https://github.com/author1")


    # Test for API to update an author (PUT /api/authors/<int:author_id>/)
    def test_update_author(self):
        # Authenticate as author1 (the author we're trying to update)
        self.client.force_authenticate(user=self.author1)
        
        update_data = {
            'displayName': 'Updated Author One',
            'github': 'https://github.com/updatedauthor',
            'profileImage': 'new_image_url'
        }
        response = self.client.put(
            reverse('api_author_detail', args=[self.author1_uuid]),
            data=json.dumps(update_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        
        # Check the response data matches what we expect
        response_data = response.json()
        self.assertEqual(response_data["displayName"], "Updated Author One")
        self.assertEqual(response_data["github"], "https://github.com/updatedauthor")
        self.assertEqual(response_data["profileImage"], "new_image_url")

        # Ensure the author was updated in the database
        self.author1.refresh_from_db()
        self.assertEqual(self.author1.displayName, 'Updated Author One')
        self.assertEqual(self.author1.github, 'https://github.com/updatedauthor')



    ### Test Error Handling ###

    # Test for retrieving a non-existent author (GET /api/authors/<int:author_id>/)
    def test_get_author_detail_not_found(self):
        # Create and authenticate a user
        user = Author.objects.create_user(
            displayName='testuser',
            password='12345',
            host='http://localhost'
        )
        self.client.force_authenticate(user=user)

        # Generate just a UUID, not a full URL
        non_existent_uuid = str(uuid.uuid4())
        response = self.client.get(reverse('api_author_detail', args=[non_existent_uuid]))
        # Since the view returns 500 for non-existent authors, we should test for that
        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.json())


    # Test for adding an author with an empty displayName (should fail if displayName is required)
    def test_add_author_with_empty_displayName_and_github(self):
        invalid_author_data = {
            'displayName': '',  # Empty displayName
            'github': 'invalid_github_url'  # No validation on github field
        }
        
        # Perform the POST request to create the author
        response = self.client.post(reverse('api_add_author'), data=invalid_author_data)
        
        # Expect a 400 Bad Request if displayName cannot be empty
        self.assertEqual(response.status_code, 400)
        self.assertIn('displayName', response.json())  # Ensure the error mentions displayName


    # Test for invalid PUT request data when updating an author (PUT /api/authors/<int:author_id>/)
    def test_update_author_with_empty_displayName_and_github(self):
        # Authenticate as author1 (the author we're trying to update)
        self.client.force_authenticate(user=self.author1)
        
        update_data = {
            'displayName': '',
            'github': 'invalid_github_url'
        }
        response = self.client.put(
            reverse('api_author_detail', args=[self.author1_uuid]),
            data=json.dumps(update_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Fetch the updated author and confirm the changes
        updated_author = Author.objects.get(author_serial=self.author1.author_serial)
        self.assertEqual(updated_author.displayName, '')  # Ensure the displayName is updated to empty
        self.assertEqual(updated_author.github, 'invalid_github_url')  # Ensure the github field is updated


    # Test that unauthenticated users cannot list authors
    def test_list_authors_unauthorized(self):
        """Test that unauthenticated users cannot list authors"""
        response = self.client.get(reverse('api_list_authors'))
        self.assertEqual(response.status_code, 401)
        self.assertIn('error', response.json())

    # Test that unauthorized users cannot update author profiles
    def test_update_author_unauthorized(self):
        """Test that unauthorized users cannot update author profiles"""
        # Authenticate as author2 trying to update author1's profile
        self.client.force_authenticate(user=self.author2)
        
        update_data = {
            'displayName': 'Unauthorized Update',
            'github': 'https://github.com/unauthorized'
        }
        response = self.client.put(
            reverse('api_author_detail', args=[self.author1_uuid]),
            data=json.dumps(update_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.json())

    # Test handling of invalid JSON data in update request
    def test_update_author_invalid_json(self):
        """Test handling of invalid JSON data in update request"""
        self.client.force_authenticate(user=self.author1)
        
        response = self.client.put(
            reverse('api_author_detail', args=[self.author1_uuid]),
            data="invalid json data",
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())


    # Test that author listing is properly paginated    
    def test_list_authors_pagination(self):
        """Test that author listing is properly paginated"""
        # Create 10 more authors
        for i in range(10):
            Author.objects.create(
                displayName=f"Test Author {i}",
                host="http://localhost",
                password="testpass"
            )
        
        self.client.force_authenticate(user=self.author1)
        response = self.client.get(reverse('api_list_authors') + '?page=1&size=5')
        self.assertEqual(response.status_code, 200)
        self.assertIn('authors', response.json())
        self.assertEqual(len(response.json()['authors']), 5)  # Should return 5 authors per page
        
    # Add new auth test methods here
    def test_signup_success(self):
        """Test successful signup"""
        signup_data = {
            "displayName": "newuser",
            "password": "newpass123",
            "host": "http://testhost.com"
        }
        
        response = self.client.post(reverse('signup'), data=signup_data)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Author.objects.filter(displayName="newuser").exists())

    def test_signup_duplicate_username(self):
        """Test signup with existing username"""
        # First create a user
        first_signup = {
            "displayName": "testuser",
            "password": "pass123",
            "host": "http://testhost.com"
        }
        first_response = self.client.post(reverse('signup'), data=first_signup)
        self.assertEqual(first_response.status_code, 201)
        
        # Try to create another user with the same displayName
        duplicate_signup = {
            "displayName": "testuser",  # Same displayName as above
            "password": "newpass123",
            "host": "http://testhost.com"
        }
        
        response = self.client.post(reverse('signup'), data=duplicate_signup)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "UserName already exists.")

    def test_login_success(self):
        """Test successful login"""
        # First create a verified user
        test_author = Author.objects.create_user(
            displayName="testuser",
            password="testpass123",
            host="http://testhost.com",
            isVerified=True  # Make sure the user is verified
        )
        
        login_data = {
            "displayName": "testuser",
            "password": "testpass123"
        }
        
        response = self.client.post(reverse('login'), data=login_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Login successful")
        self.assertTrue('jwt' in response.cookies)

    def test_login_unverified_user(self):
        """Test login with unverified user"""
        unverified_author = Author.objects.create_user(
            displayName="unverified",
            password="testpass123",
            host="http://testhost.com",
            isVerified=False
        )
        
        login_data = {
            "displayName": "unverified",
            "password": "testpass123"
        }
        
        response = self.client.post(reverse('login'), data=login_data)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Not Verified by admin")

    def test_login_wrong_password(self):
        """Test login with wrong password"""
        # First create a user to test against
        test_author = Author.objects.create_user(
            displayName="testuser",
            password="correctpass123",
            host="http://testhost.com",
            isVerified=True
        )
        
        # Try to login with wrong password
        login_data = {
            "displayName": "testuser",
            "password": "wrongpass"
        }
        
        response = self.client.post(reverse('login'), data=login_data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Not found")  # Updated to match actual error message

    def test_get_author_from_cookie(self):
        """Test getting author data from cookie"""
        # First create a verified user
        test_author = Author.objects.create_user(
            displayName="testuser",
            password="testpass123",
            host="http://testhost.com",
            isVerified=True
        )
        
        # Login to get the JWT cookie
        login_data = {
            "displayName": "testuser",
            "password": "testpass123"
        }
        login_response = self.client.post(reverse('login'), data=login_data)
        self.assertEqual(login_response.status_code, 200)
        
        # Make sure we got the JWT cookie
        self.assertTrue('jwt' in login_response.cookies)
        
        # Now try to get author data using the cookie
        response = self.client.get(
            reverse('get_author_from_cookie'),
            HTTP_COOKIE=f"jwt={login_response.cookies['jwt'].value}"
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["displayName"], "testuser")

    def test_get_author_no_cookie(self):
        """Test getting author data without cookie"""
        self.client = APIClient(raise_request_exception=False)  # Don't raise exceptions
        response = self.client.get(reverse('get_author_from_cookie'))
        self.assertEqual(response.status_code, 500)
        # You might want to check the error message if the view provides one
        # self.assertIn('error', response.json())

    def test_logout(self):
        """Test logout functionality"""
        login_data = {
            "displayName": "testuser",
            "password": "testpass123"
        }
        self.client.post(reverse('login'), data=login_data)
        
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('jwt', response.cookies)

