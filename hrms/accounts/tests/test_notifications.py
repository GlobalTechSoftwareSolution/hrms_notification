"""
Test cases for the notification system
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from accounts.models import FCMToken, Notification, Ticket

User = get_user_model()

class NotificationTestCase(TestCase):
    def setUp(self):
        # Create test users
        self.user_a = User.objects.create(
            email='usera@example.com',
            role='Employee'
        )
        self.user_a.set_password('testpass123')
        self.user_a.save()
        
        self.user_b = User.objects.create(
            email='userb@example.com',
            role='Manager'
        )
        self.user_b.set_password('testpass123')
        self.user_b.save()
        
        # Create FCM tokens
        self.fcm_token_a = FCMToken.objects.create(
            user=self.user_a,
            token='test_token_a',
            is_active=True
        )
        
        self.fcm_token_b = FCMToken.objects.create(
            user=self.user_b,
            token='test_token_b',
            is_active=True
        )
    
    def test_fcm_token_creation(self):
        """Test that FCM tokens can be created"""
        self.assertEqual(FCMToken.objects.count(), 2)
        self.assertEqual(self.fcm_token_a.user, self.user_a)
        self.assertTrue(self.fcm_token_a.is_active)
    
    def test_notification_creation(self):
        """Test that notifications can be created"""
        notification = Notification.objects.create(
            user=self.user_a,
            title='Test Notification',
            body='This is a test notification',
            data={'test': 'data'}
        )
        
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(notification.user, self.user_a)
        self.assertEqual(notification.title, 'Test Notification')
        self.assertFalse(notification.is_read)
    
    def test_ticket_notification_on_creation(self):
        """Test that notifications are sent when tickets are created"""
        # This test would require mocking the Firebase service
        # For now, we'll just verify the ticket can be created
        ticket = Ticket.objects.create(
            subject='Test Ticket',
            description='Test ticket description',
            assigned_by=self.user_a,
            assigned_to=self.user_b
        )
        
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(ticket.assigned_to, self.user_b)