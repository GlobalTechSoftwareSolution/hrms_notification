# Firebase Credentials Configuration

This document explains how to properly configure Firebase credentials for the HRMS notification system.

## Security Notice

**NEVER commit actual Firebase service account credentials to the repository.** Doing so is a serious security risk that can compromise your entire Firebase project.

## Configuration Options

### Option 1: Environment Variable (Recommended for Development)

For local development, you can set the Firebase credentials as a JSON string in your `.env` file:

```ini
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"your-project-id","private_key_id":"your-private-key-id","private_key":"-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n","client_email":"your-service-account@your-project-id.iam.gserviceaccount.com","client_id":"your-client-id","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project-id.iam.gserviceaccount.com"}
```

### Option 2: File Path (For Production)

For production environments, store the credentials in a secure location outside the project directory and reference them with an absolute path:

```ini
FIREBASE_SERVICE_ACCOUNT_KEY=/secure/path/to/firebase-service-account.json
```

## Setting Up Firebase Service Account

1. Go to the Firebase Console
2. Navigate to Project Settings > Service Accounts
3. Click "Generate new private key"
4. Save the JSON file in a secure location
5. Use one of the configuration options above

## Testing Notifications

When Firebase is not configured, the application will log a warning and skip sending notifications. This allows the application to function normally even without Firebase credentials.