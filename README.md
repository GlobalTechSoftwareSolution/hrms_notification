# HRMS Backend

## Table of Contents
- [About](#about)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Deployment](#deployment)
- [Scalability Features](#scalability-features)

## About
This is the backend for the HRMS (Human Resource Management System) application. It provides RESTful APIs for managing employee data, attendance, leave requests, payroll, and notifications.

## Features
- Employee Management
- Attendance Tracking
- Leave Management
- Payroll Processing
- Notifications (Email, SMS, FCM)
- Resignation & Offboarding
- Reporting & Analytics

## Prerequisites
- Python 3.8+
- PostgreSQL database
- MinIO server for media storage

## Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd hrms_backend
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables (see [Environment Variables](#environment-variables) section)

5. Run migrations:
   ```bash
   python manage.py migrate
   ```

6. Create superuser:
   ```bash
   python manage.py createsuperuser
   ```

7. Start the development server:
   ```bash
   python manage.py runserver
   ```

## Environment Variables

### Setting up Environment Variables
For security reasons, all sensitive configuration should be stored in environment variables and **never committed to version control**.

To set up your environment:
1. Copy the `.env.template` file to create your local `.env` file:
   ```bash
   cp hrms/.env.template hrms/.env  # On Windows: copy hrms\.env.template hrms\.env
   ```
   
2. Edit the `.env` file and replace the placeholder values with your actual configuration.

**Important:** The `.env` file is included in `.gitignore` and will not be committed to the repository.

### Required Variables
```bash
# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=*

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# CORS/CSRF
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000

# Email (SMTP)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
FRONTEND_URL=https://your-frontend-domain
LOGO_URL=https://your-logo-url

# MinIO
MINIO_ENDPOINT=your-minio-endpoint
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key
MINIO_BUCKET_NAME=your-bucket-name
MINIO_USE_SSL=True
BASE_BUCKET_URL=your-base-bucket-url

# Firebase
FIREBASE_SERVICE_ACCOUNT_KEY=/path/to/secure/firebase-service-account.json
MINIO_ENDPOINT=minio.yourdomain.com:9000
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key
MINIO_BUCKET_NAME=hrms-media
MINIO_USE_SSL=True
BASE_BUCKET_URL=https://minio.yourdomain.com:9000/hrms-media/

# Media
MEDIA_URL=/media/
```

### Sensitive Files
- `.env` - Contains all secrets and should be in `.gitignore`
- `firebase-service-account.json` - Firebase credentials should be stored securely

For proper Firebase configuration, place your `firebase-service-account.json` file in the `hrms/` directory and reference it in your `.env` file.

### Production Deployment
For production, store sensitive files outside the project directory and reference them with absolute paths.

## Deployment

### Deployment Steps
1. Install dependencies: `pip install -r requirements.txt`
2. Run migrations: `python manage.py migrate`
3. Create superuser: `python manage.py createsuperuser`
4. Start server: `gunicorn hrms.wsgi:application`

## Scalability Features

- APScheduler for background task processing
- Efficient database queries with proper indexing
- Caching strategies for frequently accessed data
- Horizontal scaling support through Gunicorn

## 🔒 Security Measures

- JWT token authentication
- CSRF protection
- SQL injection prevention through Django ORM
- XSS protection in templates
- Secure password handling
- Role-based access control

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a pull request

## 📄 License

This project is proprietary to Global Tech Software Solutions and is not available for public use or distribution.

## 📞 Support

For support, contact the HR department at hrglobaltechsoftwaresolutions@gmail.com