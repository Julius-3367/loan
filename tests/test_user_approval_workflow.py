"""
Test User Approval Workflow

Tests the complete workflow for new user registration requiring admin approval:
1. New user registers → account created with is_active=False
2. User cannot login (account pending approval)
3. Admin approves user → is_active=True
4. User can now login successfully
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.messages import get_messages
from core.models import User


class UserApprovalWorkflowTest(TestCase):
    """Test suite for user registration approval workflow"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.client = Client()
        
        # Create admin user for approval actions
        self.admin = User.objects.create_superuser(
            email='admin@albacapital.com',
            password='admin123',
            first_name='Admin',
            last_name='User'
        )
        
        # Registration data for testing
        self.registration_data = {
            'email': 'newuser@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone': '+254712345678',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
        }
        
        self.login_data = {
            'username': 'newuser@example.com',  # LoginForm uses 'username' field
            'password': 'TestPass123!',
        }
    
    def test_new_registration_creates_inactive_user(self):
        """Test that new customer registrations are created with is_active=False"""
        
        # Register new user
        response = self.client.post(reverse('register'), self.registration_data)
        
        # Check redirect to login page
        self.assertRedirects(response, reverse('login'))
        
        # Verify user was created
        user = User.objects.get(email='newuser@example.com')
        self.assertIsNotNone(user)
        
        # Verify user is inactive (pending approval)
        self.assertFalse(user.is_active, "New registration should have is_active=False")
        
        # Verify user role is CUSTOMER
        self.assertEqual(user.role, User.CUSTOMER)
        
        # Check success message mentions approval
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('pending approval' in str(m).lower() for m in messages),
            "Registration success message should mention pending approval"
        )
    
    def test_inactive_user_cannot_login(self):
        """Test that users with is_active=False cannot login"""
        
        # Create inactive user
        User.objects.create_user(
            email='newuser@example.com',
            password='TestPass123!',
            first_name='John',
            last_name='Doe',
            is_active=False
        )
        
        # Attempt to login
        response = self.client.post(reverse('login'), self.login_data, follow=True)
        
        # Verify user is NOT logged in
        self.assertFalse(response.context['user'].is_authenticated)
        
        # Check error message about pending approval
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('pending approval' in str(m).lower() for m in messages),
            "Login should show pending approval message for inactive users"
        )
    
    def test_approved_user_can_login(self):
        """Test that admin approval (is_active=True) allows user to login"""
        
        # Create inactive user
        user = User.objects.create_user(
            email='newuser@example.com',
            password='TestPass123!',
            first_name='John',
            last_name='Doe',
            is_active=False
        )
        
        # Admin approves user
        user.is_active = True
        user.save()
        
        # Attempt to login
        response = self.client.post(reverse('login'), self.login_data, follow=True)
        
        # Verify user IS logged in
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].email, 'newuser@example.com')
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('welcome' in str(m).lower() for m in messages),
            "Login should show welcome message for approved users"
        )
    
    def test_admin_created_users_are_active(self):
        """Test that staff users created by admin are active by default"""
        
        # Login as admin
        self.client.login(email='admin@albacapital.com', password='admin123')
        
        # Create staff user via UserManager (simulating admin creation)
        staff_user = User.objects.create_user(
            email='staff@albacapital.com',
            password='staff123',
            first_name='Staff',
            last_name='User',
            role=User.CREDIT_OFFICER,
            is_staff=True,
            is_active=True  # Admin explicitly sets this
        )
        
        # Verify staff user is active
        self.assertTrue(staff_user.is_active, "Staff users should be active when created by admin")
        
        # Verify staff user can login
        self.client.logout()
        login_success = self.client.login(email='staff@albacapital.com', password='staff123')
        self.assertTrue(login_success, "Staff users should be able to login immediately")
    
    def test_approval_workflow_complete(self):
        """Test complete workflow: Register → Cannot Login → Approve → Can Login"""
        
        # Step 1: Register new user
        self.client.post(reverse('register'), self.registration_data)
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.is_active)
        
        # Step 2: Attempt login (should fail)
        response = self.client.post(reverse('login'), self.login_data)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        
        # Step 3: Admin approves user
        user.is_active = True
        user.save()
        
        # Step 4: Login again (should succeed)
        response = self.client.post(reverse('login'), self.login_data, follow=True)
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].email, 'newuser@example.com')
        
        # Verify redirect to customer dashboard
        self.assertRedirects(
            response,
            reverse('customer_dashboard'),
            fetch_redirect_response=False
        )
    
    def test_rejected_user_remains_inactive(self):
        """Test that rejected users (is_active=False) cannot login"""
        
        # Create and then reject user
        user = User.objects.create_user(
            email='rejected@example.com',
            password='TestPass123!',
            first_name='Rejected',
            last_name='User',
            is_active=True
        )
        
        # Admin rejects/deactivates user
        user.is_active = False
        user.save()
        
        # Attempt to login
        login_data = {
            'username': 'rejected@example.com',
            'password': 'TestPass123!',
        }
        response = self.client.post(reverse('login'), login_data, follow=True)
        
        # Verify user cannot login
        self.assertFalse(response.context['user'].is_authenticated)
        
        # Check appropriate error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('pending approval' in str(m).lower() for m in messages),
            "Rejected users should see pending approval message"
        )
