# Firebase Notifications Implementation

This document explains how to use the Firebase notification system implemented in the HRMS backend.

## Overview

The notification system allows the HRMS to send real-time notifications to users via Firebase Cloud Messaging (FCM). It includes:

1. FCM token registration and management
2. Notification sending service
3. Notification history tracking
4. Integration with ticket assignments

## Setup

### 1. Firebase Configuration

1. Create a Firebase project at https://console.firebase.google.com/
2. Download the service account key JSON file
3. Place the file in your project directory
4. Set the `FIREBASE_SERVICE_ACCOUNT_KEY` environment variable to point to this file

### 2. Frontend Integration

To receive notifications in your frontend application:

1. Install the Firebase SDK:
   ```bash
   npm install firebase
   ```

2. Initialize Firebase in your frontend application:
   ```javascript
   import { initializeApp } from 'firebase/app';
   import { getMessaging, getToken, onMessage } from 'firebase/messaging';

   // Your web app's Firebase configuration
   const firebaseConfig = {
     apiKey: "YOUR_API_KEY",
     authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
     projectId: "YOUR_PROJECT_ID",
     storageBucket: "YOUR_PROJECT_ID.appspot.com",
     messagingSenderId: "YOUR_SENDER_ID",
     appId: "YOUR_APP_ID"
   };

   // Initialize Firebase
   const app = initializeApp(firebaseConfig);
   const messaging = getMessaging(app);
   ```

3. Request permission and get FCM token:
   ```javascript
   async function requestNotificationPermission() {
     try {
       const permission = await Notification.requestPermission();
       if (permission === 'granted') {
         const token = await getToken(messaging, {
           vapidKey: 'YOUR_VAPID_KEY'
         });
         
         // Send token to backend
         await fetch('/api/accounts/register_fcm_token/', {
           method: 'POST',
           headers: {
             'Content-Type': 'application/json',
           },
           body: JSON.stringify({
             email: 'user@example.com',
             token: token
           })
         });
       }
     } catch (error) {
       console.error('Error requesting notification permission:', error);
     }
   }
   ```

4. Handle incoming messages:
   ```javascript
   onMessage(messaging, (payload) => {
     console.log('Message received:', payload);
     // Display notification to user
     new Notification(payload.notification.title, {
       body: payload.notification.body
     });
   });
   ```

## API Endpoints

### 1. Register FCM Token
- **URL**: `/api/accounts/register_fcm_token/`
- **Method**: `POST`
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "token": "FCM_TOKEN"
  }
  ```
- **Response**:
  ```json
  {
    "message": "FCM token registered successfully",
    "token_id": 1
  }
  ```

### 2. Unregister FCM Token
- **URL**: `/api/accounts/unregister_fcm_token/`
- **Method**: `POST`
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "token": "FCM_TOKEN"
  }
  ```
- **Response**:
  ```json
  {
    "message": "FCM token unregistered successfully"
  }
  ```

### 3. Get User Notifications
- **URL**: `/api/accounts/notifications/{email}/`
- **Method**: `GET`
- **Response**:
  ```json
  [
    {
      "id": 1,
      "title": "New Ticket Assigned",
      "body": "You have been assigned a new ticket: Fix login issue",
      "data": {
        "ticket_id": "123",
        "notification_type": "ticket_assigned"
      },
      "is_read": false,
      "created_at": "2025-11-12T12:00:00Z",
      "updated_at": "2025-11-12T12:00:00Z"
    }
  ]
  ```

### 4. Mark Notification as Read
- **URL**: `/api/accounts/notifications/{notification_id}/read/`
- **Method**: `PATCH`
- **Response**:
  ```json
  {
    "id": 1,
    "title": "New Ticket Assigned",
    "body": "You have been assigned a new ticket: Fix login issue",
    "data": {
      "ticket_id": "123",
      "notification_type": "ticket_assigned"
    },
    "is_read": true,
    "created_at": "2025-11-12T12:00:00Z",
    "updated_at": "2025-11-12T12:05:00Z"
  }
  ```

### 5. Mark All Notifications as Read
- **URL**: `/api/accounts/notifications/{email}/read_all/`
- **Method**: `PATCH`
- **Response**:
  ```json
  {
    "message": "Marked 5 notifications as read"
  }
  ```

## How It Works

1. When a user logs in, the frontend requests notification permission and gets an FCM token
2. The FCM token is sent to the backend and stored in the database
3. When a ticket is assigned, updated, or closed, a notification is sent via FCM
4. Notifications are also stored in the database for history tracking
5. Users can fetch their notification history via the API
6. Users can mark notifications as read to keep track of what they've seen

## Notification Types

The system currently sends notifications for:

1. **Ticket Assignment**: When a user is assigned a new ticket
2. **Ticket Updates**: When a ticket assigned to a user is updated
3. **Ticket Closure**: When a ticket assigned to a user is closed

## Extending the System

To add notifications for other events:

1. Modify the `notification_service.py` file to add new notification functions
2. Call these functions from the appropriate places in your code (e.g., when creating a leave request)
3. Add any necessary data to the notification payload
4. Update the frontend to handle the new notification types

## Error Handling

The system handles several error cases:

1. Invalid FCM tokens are automatically deactivated
2. Failed notification sends are logged for debugging
3. Database errors are caught and logged
4. Network errors are handled gracefully

## Security Considerations

1. FCM tokens are associated with specific users
2. Only the token owner can mark their notifications as read
3. Firebase service account keys should be kept secure
4. HTTPS should be used in production to protect token transmission