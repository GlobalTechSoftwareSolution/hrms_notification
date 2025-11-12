# Global Tech HRMS Backend

A comprehensive Human Resource Management System built with Django REST Framework, providing complete employee lifecycle management from onboarding to offboarding.

## 🏢 Overview

The Global Tech HRMS Backend is a robust, scalable solution for managing all aspects of human resources in an organization. It features a complete employee management system with role-based access control, attendance tracking, leave management, payroll processing, and a sophisticated two-stage resignation approval workflow.

## 🚀 Key Features

### 🔐 Authentication & Authorization
- Role-based access control (Employee, Manager, HR, Admin, CEO)
- JWT token authentication
- Secure password reset functionality
- Custom user model implementation

### 👥 Employee Management
- Complete employee profiles with personal and professional details
- Document management system (resumes, certificates, letters)
- Employee awards and recognition tracking
- Multi-role support with specialized data models

### 📅 Attendance & Time Tracking
- Location-based attendance verification
- Office and work-from-home tracking
- Automated absent marking
- Detailed attendance reports

### 📋 Leave Management
- Leave application and approval workflow
- Multiple leave types support
- Leave balance tracking
- Integrated calendar view

### 💰 Payroll System
- Salary calculation and processing
- Monthly payroll generation
- Payment status tracking
- Loss of Pay (LOP) calculations

### 📊 Task & Project Management
- Task assignment and tracking
- Project collaboration tools
- Progress monitoring
- Reporting system

### 🎓 Recruitment & Career Portal
- Job posting management
- Candidate application tracking
- Hiring workflow
- Training availability tracking

### 📤 Resignation & Offboarding
- Two-stage approval workflow (Manager → HR)
- Comprehensive audit trail preservation
- Automated email notifications at each stage
- Document retention for rejected applications
- Proper data cleanup upon final approval

## 🛠️ Technology Stack

- **Framework**: Django 5.2.6
- **API**: Django REST Framework
- **Database**: PostgreSQL (configured via dj_database_url)
- **Authentication**: Django REST Framework Simple JWT
- **Storage**: MinIO (S3 Compatible) for media files
- **Background Tasks**: APScheduler
- **Email**: SMTP (Gmail)
- **Frontend Integration**: CORS enabled for React/Vue applications
- **Deployment**: Gunicorn, Whitenoise for static files

## 📁 Project Structure

```
hrms/
├── accounts/                 # Main application
│   ├── models.py            # All data models
│   ├── views.py             # API endpoints
│   ├── serializers.py       # Data serialization
│   ├── urls.py              # URL routing
│   ├── templates/           # Email and document templates
│   └── migrations/          # Database migrations
├── hrms/                    # Project settings
│   ├── settings.py          # Configuration
│   └── urls.py              # Main URL routing
├── manage.py               # Django management script
├── requirements.txt        # Python dependencies
└── Procfile               # Deployment configuration
```

## 🔄 Core Workflows

### Employee Onboarding
1. User registration and approval
2. Role assignment (Employee, Manager, HR, etc.)
3. Profile completion with personal details
4. Document upload (ID proofs, certificates)
5. Department and team assignment

### Attendance Management
1. Location-verified check-in/check-out
2. Automatic absent marking after deadline
3. Work-from-home tracking
4. Attendance reporting and analytics

### Leave Processing
1. Leave application submission
2. Manager approval workflow
3. Automatic balance updates
4. Leave history tracking

### Resignation Process
A sophisticated two-stage approval system:
1. **Stage 1 - Manager Approval**:
   - Employee submits resignation
   - Manager reviews and approves/rejects
   - Automatic notification to employee
2. **Stage 2 - HR Approval**:
   - HR reviews manager-approved resignations
   - Final approval triggers offboarding
   - Complete data cleanup and notifications

### Offboarding
1. Data archival in ReleavedEmployee table
2. Profile picture deletion from MinIO
3. User account and related data cleanup
4. Leadership notifications

## 📧 Email Notifications

The system includes comprehensive email templates for all major events:
- Password reset requests
- Resignation approvals and rejections
- Manager and HR level notifications
- Offboarding confirmations
- Leadership notifications

## 🔧 API Endpoints

### Authentication
- `POST /api/accounts/signup/` - User registration
- `POST /api/accounts/login/` - User login
- `POST /api/accounts/password_reset/` - Password reset request
- `POST /api/accounts/password_reset_confirm/` - Password reset confirmation

### Employee Management
- `GET/POST /api/accounts/employees/` - Employee list/create
- `GET/PATCH/DELETE /api/accounts/employees/<email>/` - Employee details/update/delete
- Similar endpoints for HR, Manager, Admin, and CEO roles

### Attendance
- `POST /api/accounts/office_attendance/` - Office check-in
- `POST /api/accounts/work_attendance/` - Work-from-home check-in
- `GET /api/accounts/today_attendance/` - Today's attendance
- `GET /api/accounts/list_attendance/` - Attendance history

### Leave Management
- `POST /api/accounts/apply_leave/` - Apply for leave
- `PATCH /api/accounts/update_leave/<id>/` - Update leave status
- `GET /api/accounts/list_leaves/` - List all leaves

### Resignation & Offboarding
- `POST /api/accounts/releaved/` - Initiate resignation
- `PATCH /api/accounts/releaved/<id>/` - Approve/reject resignation (manager/HR)
- `GET /api/accounts/list_releaved/` - List resigned employees
- `GET /api/accounts/get_releaved/<id>/` - Get resigned employee details

## 🔒 Security Best Practices

### Environment Variables
All sensitive configuration should be stored in environment variables and **never committed to version control**. Use the `.env.template` file as a reference for required variables.

### Sensitive Files
- `.env` - Contains all secrets and should be in `.gitignore`
- `firebase-service-account.json` - Firebase credentials should be stored securely

### Production Deployment
For production, store sensitive files outside the project directory and reference them with absolute paths.

## 🚀 Deployment

### Prerequisites
- Python 3.8+
- PostgreSQL database
- MinIO server for media storage

### Environment Variables
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

### Deployment Steps
1. Install dependencies: `pip install -r requirements.txt`
2. Run migrations: `python manage.py migrate`
3. Create superuser: `python manage.py createsuperuser`
4. Start server: `gunicorn hrms.wsgi:application`

## 📈 Scalability Features

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