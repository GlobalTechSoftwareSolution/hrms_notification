# FCM Push Notifications Implementation

This document describes how to set up and use Firebase Cloud Messaging (FCM) push notifications in the HRMS application.

## Setup Instructions

### 1. Install Required Packages

The following packages are required for FCM functionality:

```bash
pip install firebase-admin python-decouple
```

These have already been added to the requirements.txt file.

### 2. Firebase Configuration

1. Create a Firebase project at https://console.firebase.google.com/
2. Generate a service account key:
   - Go to Project Settings > Service Accounts
   - Click "Generate new private key"
   - Save the JSON file as `firebase_service_account.json`
3. Place the file in the project root directory (`hrms_backend/hrms/`)

### 3. Environment Variables

Add the following to your `.env` file:

```env
FIREBASE_CREDENTIALS_PATH=firebase_service_account.json
```

## API Endpoints

### Register FCM Token
Registers or updates an FCM token for a user.

**Endpoint:** `POST /accounts/fcm/register/`

**Request Body:**
```json
{
  "email": "user@example.com",
  "token": "fcm_token_string",
  "device_type": "android"  // or "ios"
}
```

### Unregister FCM Token
Removes an FCM token (used during logout).

**Endpoint:** `POST /accounts/fcm/unregister/`

**Request Body:**
```json
{
  "email": "user@example.com",
  "device_type": "android"  // or "ios"
}
```

### Send Notification to User
Sends a push notification to a specific user.

**Endpoint:** `POST /accounts/fcm/send_to_user/`

**Request Body:**
```json
{
  "email": "user@example.com",
  "title": "Notification Title",
  "body": "Notification Body",
  "data": {
    "key": "value"
  }
}
```

### Send Notification to Topic
Sends a push notification to a topic.

**Endpoint:** `POST /accounts/fcm/send_to_topic/`

**Request Body:**
```json
{
  "topic": "news",
  "title": "Notification Title",
  "body": "Notification Body",
  "data": {
    "key": "value"
  }
}
```

## Database Model

The `FCMToken` model stores tokens with the following fields:

- `email`: Foreign key to User model
- `token`: The FCM token string
- `device_type`: Either "android" or "ios"
- `created_at`: Timestamp when the token was registered
- `updated_at`: Timestamp when the token was last updated

## Implementation Details

1. **Token Storage**: Tokens are stored in the database and associated with users and device types
2. **Duplicate Handling**: If a user registers a new token for the same device type, the old token is replaced
3. **Error Handling**: Invalid tokens are automatically removed from the database
4. **Security**: All endpoints require valid user authentication

## Testing

To test the FCM implementation:

1. Register a token using the `/accounts/fcm/register/` endpoint
2. Send a notification using the `/accounts/fcm/send_to_user/` endpoint
3. Verify the notification is received on the device

## Troubleshooting

1. **Firebase credentials not found**: Ensure the service account JSON file exists and the path is correctly configured
2. **Tokens not saving**: Check database permissions and model validation
3. **Notifications not sending**: Verify the FCM token is valid and the device is properly configured to receive notifications