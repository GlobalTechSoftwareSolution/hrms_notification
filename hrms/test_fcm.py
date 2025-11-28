"""
Test script for FCM implementation
This script demonstrates how to use the FCM functionality
"""

import os
import sys
import django
from django.conf import settings

# Add the project directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hrms.settings')
django.setup()

from accounts.models import FCMToken, User
from accounts.serializers import FCMTokenSerializer
from django.core.exceptions import ValidationError

def test_fcm_model():
    """Test FCMToken model creation"""
    print("Testing FCMToken model...")
    
    # Create a test user (if not exists)
    user, created = User.objects.get_or_create(
        email="test@example.com",
        defaults={
            "role": "employee",
            "is_staff": True
        }
    )
    
    if created:
        user.set_password("testpass123")
        user.save()
        print("Created test user")
    
    # Create FCM token
    try:
        fcm_token = FCMToken.objects.create(
            email=user,
            token="test_fcm_token_12345",
            device_type="android"
        )
        print("✓ FCMToken created successfully")
        
        # Test serializer
        serializer = FCMTokenSerializer(fcm_token)
        print("✓ FCMToken serializer works")
        print(f"Serialized data: {serializer.data}")
        
        # Test update or create
        fcm_token_updated, created = FCMToken.objects.update_or_create(
            email=user,
            device_type="android",
            defaults={"token": "updated_test_fcm_token_67890"}
        )
        
        if created:
            print("✓ FCMToken created with update_or_create")
        else:
            print("✓ FCMToken updated with update_or_create")
            
        # Clean up
        fcm_token.delete()
        print("✓ FCMToken cleanup completed")
        
    except Exception as e:
        print(f"✗ Error testing FCMToken model: {e}")

def test_fcm_views():
    """Test FCM views functionality"""
    print("\nTesting FCM views...")
    print("Note: View testing requires Django test client or HTTP requests")
    print("Implement with Django TestCase for full testing")

if __name__ == "__main__":
    print("Running FCM Implementation Tests")
    print("=" * 40)
    
    test_fcm_model()
    test_fcm_views()
    
    print("\n" + "=" * 40)
    print("FCM Implementation Tests Completed")