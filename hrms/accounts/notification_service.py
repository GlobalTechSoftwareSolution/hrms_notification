import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from .models import FCMToken, User, Notification
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        if not firebase_admin._apps:
            # Check if FIREBASE_SERVICE_ACCOUNT_KEY is a dict (JSON) or string (file path)
            if isinstance(settings.FIREBASE_SERVICE_ACCOUNT_KEY, dict):
                # Use JSON credentials directly
                cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
            else:
                # Use the service account key file
                cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {str(e)}")

def send_fcm_notification(user_email, title, body, data=None):
    """
    Send FCM notification to a specific user
    """
    try:
        # Initialize Firebase if not already done
        initialize_firebase()
        
        # Get active FCM tokens for the user
        user = User.objects.get(email=user_email)
        fcm_tokens = FCMToken.objects.filter(user=user, is_active=True)
        
        if not fcm_tokens.exists():
            logger.info(f"No active FCM tokens found for user {user_email}")
            return False
        
        # Save notification to database
        notification = Notification.objects.create(
            user=user,
            title=title,
            body=body,
            data=data or {}
        )
        
        # Send notification to each token
        for token_obj in fcm_tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=data or {},
                    token=token_obj.token,
                )
                
                response = messaging.send(message)
                logger.info(f"Successfully sent message: {response}")
            except Exception as e:
                logger.error(f"Failed to send FCM message to token {token_obj.token}: {str(e)}")
                # Deactivate invalid tokens
                if "invalid" in str(e).lower() or "not registered" in str(e).lower():
                    token_obj.is_active = False
                    token_obj.save()
        
        return True
    except User.DoesNotExist:
        logger.error(f"User with email {user_email} does not exist")
        return False
    except Exception as e:
        logger.error(f"Error sending FCM notification: {str(e)}")
        return False

def send_ticket_notification(ticket, notification_type="assigned"):
    """
    Send notification for ticket assignment or updates
    """
    try:
        if notification_type == "assigned":
            title = "New Ticket Assigned"
            body = f"You have been assigned a new ticket: {ticket.subject}"
            data = {
                "ticket_id": str(ticket.id),
                "notification_type": "ticket_assigned"
            }
        elif notification_type == "updated":
            title = "Ticket Updated"
            body = f"Ticket '{ticket.subject}' has been updated"
            data = {
                "ticket_id": str(ticket.id),
                "notification_type": "ticket_updated"
            }
        elif notification_type == "closed":
            title = "Ticket Closed"
            body = f"Ticket '{ticket.subject}' has been closed"
            data = {
                "ticket_id": str(ticket.id),
                "notification_type": "ticket_closed"
            }
        else:
            return False
        
        # Send notification to assigned user
        if ticket.assigned_to:
            return send_fcm_notification(
                ticket.assigned_to.email,
                title,
                body,
                data
            )
        return False
    except Exception as e:
        logger.error(f"Error sending ticket notification: {str(e)}")
        return False