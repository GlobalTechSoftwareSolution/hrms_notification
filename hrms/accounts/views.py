import os, json, pytz, face_recognition, tempfile
import boto3

from io import BytesIO
from datetime import datetime
from geopy.distance import geodesic

from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from accounts.models import Document
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth import authenticate, get_user_model
from django.utils.dateparse import parse_date
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes

# Models
from .models import (
    User, CEO, HR, Manager, Employee, Attendance, Admin,
    Leave, Payroll, TaskTable, Project, Notice, Report,
    Document, Award
)

# Serializers
from .serializers import (
    UserSerializer, CEOSerializer, HRSerializer, ManagerSerializer,
    EmployeeSerializer, SuperUserCreateSerializer, UserRegistrationSerializer,
    AdminSerializer, ReportSerializer, RegisterSerializer, DocumentSerializer, AwardSerializer
)

# Ensure User model points to custom one
User = get_user_model()


class SignupView(APIView):
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({'user': serializer.data, 'message': 'Signup successful'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        role = request.data.get('role')
        if not email or not password or not role:
            return Response(
                {'error': 'Email, password, and role are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        user = authenticate(request, username=email, password=password)  # assumes USERNAME_FIELD='email'
        if user is not None:
            if user.role != role:
                return Response({'error': 'Role does not match'}, status=status.HTTP_403_FORBIDDEN)
            serializer = UserSerializer(user)
            return Response({'user': serializer.data, 'message': 'Login successful'}, status=status.HTTP_200_OK)
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class CreateSuperUserView(APIView):
    def post(self, request):
        serializer = SuperUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()  # Calls create_superuser method from UserManager
            return Response(
                {
                    'message': 'Superuser created successfully',
                    'email': user.email,
                    'role': user.role
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def approve_user(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email=email)
        user.is_staff = True  # Mark user as staff (approved)
        user.save()
        return Response({'success': True, 'email': email})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def reject_user(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email=email)
        user.delete()  # Delete user (rejected)
        return Response({'success': True, 'email': email})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


def get_email_by_username(username):
    username = username.lower()
    for model in [HR, Employee, CEO, Manager, Admin]:
        for obj in model.objects.all():
            full_name_lower = obj.fullname.lower()
            if any(part.startswith(username) for part in full_name_lower.split()):
                email = obj.email.email
                print(f"[get_email_by_username] Found email {email} for username {username} in {model.fullname}")
                return email
    print(f"[get_email_by_username] No email found for username {username}")
    return None


def is_email_exists(email):
    exists = any([
        HR.objects.filter(email=email).exists(),
        Employee.objects.filter(email=email).exists(),
        CEO.objects.filter(email=email).exists(),
        Manager.objects.filter(email=email).exists(),
        Admin.objects.filter(email=email).exists()
    ])
    print(f"[is_email_exists] Email {email} exists: {exists}")
    return exists


OFFICE_LAT = 13.068906816007116
OFFICE_LON = 77.55541294505542
LOCATION_RADIUS_METERS = 100  # 100m allowed radius

IST = pytz.timezone("Asia/Kolkata")

def mark_attendance_by_email(email_str, latitude=None, longitude=None):
    """
    Marks attendance for a user based on email and live location.
    Only works if user is within 100 meters of the office.
    """
    if not is_email_exists(email_str):
        print(f"[mark_attendance_by_email] Email {email_str} not found. Attendance not marked.")
        return None

    if latitude is None or longitude is None:
        print("[mark_attendance_by_email] Location not provided — attendance not marked.")
        return None

    user_location = (latitude, longitude)
    office_location = (OFFICE_LAT, OFFICE_LON)
    distance_meters = geodesic(user_location, office_location).meters

    if distance_meters > LOCATION_RADIUS_METERS:
        print(f"[mark_attendance_by_email] User {email_str} is too far ({distance_meters:.2f}m). Attendance denied.")
        return None

    today = timezone.localdate()
    now = timezone.now().astimezone(IST)
    print(f"[mark_attendance_by_email] Processing attendance for {email_str} on {today} at {now}")

    try:
        user_instance = User.objects.get(email=email_str)
    except User.DoesNotExist:
        print(f"[mark_attendance_by_email] User instance not found for {email_str}")
        return None

    try:
        attendance = Attendance.objects.get(email=user_instance, date=today)
        if attendance.check_out is None:
            attendance.check_out = now.time()
            attendance.save()
            print(f"[mark_attendance_by_email] Updated check_out for {email_str} at {now}")
    except Attendance.DoesNotExist:
        try:
            attendance = Attendance.objects.create(
                email=user_instance,
                date=today,
                check_in=now.time(),
                latitude=latitude,
                longitude=longitude,
                location_verified=True  # ✅ within 100m radius
            )
            print(f"[mark_attendance_by_email] Created new attendance record for {email_str} at {now}")
        except Exception as e:
            print(f"[mark_attendance_by_email ERROR] Failed to save attendance for {email_str}: {e}")
            return None

    return attendance


def today_attendance(request):
    today = timezone.localdate()
    attendances = Attendance.objects.filter(date=today)

    data = [
        {
            "email": att.email.email,
            "role": att.email.role,
            "fullname": att.fullname,
            "department": att.department,
            "date": str(att.date),
            "check_in": str(att.check_in) if att.check_in else "",
            "check_out": str(att.check_out) if att.check_out else ""
        }
        for att in attendances
    ]

    return JsonResponse({"attendances": data})


# Helper function to handle PATCH
def handle_patch(request, ModelClass, SerializerClass):
    try:
        data = json.loads(request.body)
        email = data.get("email")
        if not email:
            return JsonResponse({"error": "Email field is required"}, status=400)
        instance = ModelClass.objects.get(email=email)
    except ModelClass.DoesNotExist:
        return JsonResponse({"error": f"{ModelClass._name_} not found"}, status=404)

    # partial=True enables PATCH-like behavior
    serializer = SerializerClass(instance, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return JsonResponse(serializer.data)
    return JsonResponse(serializer.errors, status=400)


# Helper function to handle DELETE
def handle_delete(request, ModelClass):
    try:
        data = json.loads(request.body)
        email = data.get("email")
        if not email:
            return JsonResponse({"error": "Email field is required"}, status=400)
        
        # Get the instance in role table
        instance = ModelClass.objects.get(email=email)
        instance.delete()
        print(f"Deleted {ModelClass.name} record with email {email}")
        
        # Also delete corresponding User record
        from accounts.models import User  # import User model
        try:
            user = User.objects.get(email=email)
            user.delete()
            print(f"Deleted User record with email {email}")
        except User.DoesNotExist:
            print(f"No User record found to delete for email {email}")
        
        return JsonResponse({"message": f"{ModelClass.name} and User deleted successfully"})
    except ModelClass.DoesNotExist:
        return JsonResponse({"error": f"{ModelClass.name} not found"}, status=404)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    lookup_field = 'email'

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return UserRegistrationSerializer
        return UserSerializer


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    lookup_field = 'email'

    def partial_update(self, request, *args, **kwargs):
        employee = self.get_object()
        updated = False

        # MinIO client
        client = boto3.client(
            's3',
            endpoint_url='http://194.238.19.109:9000',
            aws_access_key_id='djangouser',
            aws_secret_access_key='django_secret_key',
        )
        bucket_name = 'hrms-media'

        # Handle profile_picture if provided
        if 'profile_picture' in request.FILES:
            file_obj = request.FILES['profile_picture']
            key = f'images/{employee.email}/profile_picture.{file_obj.name.split(".")[-1]}'

            # Upload to MinIO
            client.upload_fileobj(file_obj, bucket_name, key)

            # Store full URL in URLField
            employee.profile_picture = f'http://194.238.19.109:9000/{bucket_name}/{key}'
            updated = True

        # Update other fields
        for field, value in request.data.items():
            if hasattr(employee, field) and field != 'profile_picture':
                setattr(employee, field, value)
                updated = True

        if updated:
            employee.save()

        serializer = EmployeeSerializer(employee)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        profile_file = request.FILES.get('profile_picture')

        serializer = EmployeeSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()

        if profile_file:
            client = boto3.client(
                's3',
                endpoint_url='http://194.238.19.109:9000',
                aws_access_key_id='djangouser',
                aws_secret_access_key='django_secret_key',
            )
            bucket_name = 'hrms-media'
            ext = profile_file.name.split(".")[-1]
            key = f'images/{employee.email}/profile_picture.{ext}'
            print("Uploading to:", key)
            client.upload_fileobj(profile_file, bucket_name, key)
            print("Upload successful")

            employee.profile_picture = f'http://194.238.19.109:9000/{bucket_name}/{key}'
            employee.save()

        serializer = EmployeeSerializer(employee)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    

class HRViewSet(viewsets.ModelViewSet):
    queryset = HR.objects.all()
    serializer_class = HRSerializer
    lookup_field = 'email'


class ManagerViewSet(viewsets.ModelViewSet):
    queryset = Manager.objects.all()
    serializer_class = ManagerSerializer
    lookup_field = 'email'


class AdminViewSet(viewsets.ModelViewSet):
    queryset = Admin.objects.all()
    serializer_class = AdminSerializer
    lookup_field = 'email'


class CEOViewSet(viewsets.ModelViewSet):
    queryset = CEO.objects.all()
    serializer_class = CEOSerializer
    lookup_field = 'email'

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    lookup_field = 'email'  # use email instead of pk

class AwardViewSet(viewsets.ModelViewSet):
    queryset = Award.objects.all()
    serializer_class = AwardSerializer
    lookup_field = 'email'  # use email instead of pk


@csrf_exempt
def apply_leave(request):
    """Employee applies for leave. If overlapping leave with status Pending or Approved exists, return error."""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)
    try:
        data = json.loads(request.body)
        email = data.get("email")
        user = get_object_or_404(User, email=email)

        new_start = data.get("start_date")
        new_end = data.get("end_date")

        if not new_start or not new_end:
            return JsonResponse({"error": "Start date and end date are required."}, status=400)

        # Check for overlapping leaves with status Pending or Approved
        overlapping_leave_exists = Leave.objects.filter(
            email=user,
            status__in=['Pending', 'Approved'],
        ).filter(
            Q(start_date_lte=new_end) & Q(end_date_gte=new_start)
        ).exists()

        if overlapping_leave_exists:
            return JsonResponse({"error": "You already have a leave request overlapping requested dates."}, status=400)

        leave = Leave.objects.create(
            email=user,
            department=data.get("department"),
            start_date=new_start,
            end_date=new_end,
            leave_type=data.get("leave_type", ""),
            reason=data.get("reason", ""),
            status="Pending"
        )
        return JsonResponse({
            "message": "Leave request submitted successfully",
            "leave": {
                "email": leave.email.email,
                "department": leave.department,
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "leave_type": leave.leave_type,
                "reason": leave.reason,
                "status": leave.status
            }
        }, status=201)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def update_leave_status(request, leave_id):
    if request.method != "PATCH":
        return JsonResponse({"error": "Only PATCH method allowed"}, status=405)
    try:
        leave = get_object_or_404(Leave, id=leave_id)
        data = json.loads(request.body)
        new_status = data.get("status")

        if new_status not in ["Approved", "Rejected"]:
            return JsonResponse({"error": "Invalid status. Must be Approved or Rejected."}, status=400)

        leave.status = new_status
        leave.save()

        return JsonResponse({
            "message": f"Leave request {new_status}",
            "leave": {
                "email": leave.email.email,
                "department": leave.department,
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "leave_type": leave.leave_type,
                "reason": leave.reason,
                "status": leave.status
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def leaves_today(request):
    """List all employees on leave today"""
    if request.method != "GET":
        return JsonResponse({"error": "Only GET method allowed"}, status=405)

    today = timezone.localdate()
    leaves = Leave.objects.filter(
        status="Approved",
        start_date__lte=today,
        end_date__gte=today
    )

    result = []
    for leave in leaves:
        result.append({
            "email": leave.email.email,
            "department": leave.department,
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "leave_type": leave.leave_type,
            "reason": leave.reason,
            "status": leave.status
        })

    return JsonResponse({"leaves_today": result}, status=200)


@require_GET
def list_leaves(request):
    """List all leaves"""
    leaves = Leave.objects.all().order_by('-applied_on')

    result = []
    for leave in leaves:
        result.append({
            "id": leave.id,
            "email": leave.email.email,
            "department": leave.department,
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "leave_type": leave.leave_type,
            "reason": leave.reason,
            "status": leave.status,
            "applied_on": str(leave.applied_on)
        })

    return JsonResponse({"leaves": result}, status=200)


@csrf_exempt
def create_payroll(request):
    """Create payroll for an employee"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get("email")
        user = get_object_or_404(User, email=email)

        month = data.get("month")
        year = data.get("year", timezone.now().year)

        # Check if payroll already exists for this month/year
        if Payroll.objects.filter(email=user, month=month, year=year).exists():
            return JsonResponse({"error": "Payroll already exists for this month and year"}, status=400)

        payroll = Payroll.objects.create(
            email=user,
            basic_salary=data.get("basic_salary", 0.00),
            allowances=data.get("allowances", 0.00),
            deductions=data.get("deductions", 0.00),
            bonus=data.get("bonus", 0.00),
            tax=data.get("tax", 0.00),
            month=month,
            year=year,
            status=data.get("status", "Pending")
        )

        return JsonResponse({
            "message": "Payroll created successfully",
            "payroll": {
                "email": payroll.email.email,
                "basic_salary": str(payroll.basic_salary),
                "allowances": str(payroll.allowances),
                "deductions": str(payroll.deductions),
                "bonus": str(payroll.bonus),
                "tax": str(payroll.tax),
                "net_salary": str(payroll.net_salary),
                "month": payroll.month,
                "year": payroll.year,
                "status": payroll.status,
                "pay_date": str(payroll.pay_date)
            }
        }, status=201)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def update_payroll_status(request, payroll_id):
    """Update payroll status using payroll ID."""
    if request.method != "PATCH":
        return JsonResponse({"error": "Only PATCH method allowed"}, status=405)
    try:
        payroll = get_object_or_404(Payroll, id=payroll_id)
        data = json.loads(request.body)
        new_status = data.get("status")

        if new_status not in ["Pending", "Paid", "Failed"]:
            return JsonResponse({"error": "Invalid status"}, status=400)

        payroll.status = new_status
        payroll.save()

        return JsonResponse({
            "message": f"Payroll status updated to {new_status}",
            "payroll": {
                "email": payroll.email.email,
                "basic_salary": str(payroll.basic_salary),
                "allowances": str(payroll.allowances),
                "deductions": str(payroll.deductions),
                "bonus": str(payroll.bonus),
                "tax": str(payroll.tax),
                "net_salary": str(payroll.net_salary),
                "month": payroll.month,
                "year": payroll.year,
                "status": payroll.status,
                "pay_date": str(payroll.pay_date)
            }
        }, status=200)

    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll record not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def get_payroll(request, email):
    """Fetch payroll details for an employee"""
    if request.method != "GET":
        return JsonResponse({"error": "Only GET method allowed"}, status=405)

    user = get_object_or_404(User, email=email)
    payroll = get_object_or_404(Payroll, email=user)

    return JsonResponse({
        "payroll": {
            "email": payroll.email.email,
            "basic_salary": str(payroll.basic_salary),
            "allowances": str(payroll.allowances),
            "deductions": str(payroll.deductions),
            "bonus": str(payroll.bonus),
            "tax": str(payroll.tax),
            "net_salary": str(payroll.net_salary),
            "month": payroll.month,
            "year": payroll.year,
            "status": payroll.status,
            "pay_date": str(payroll.pay_date)
        }
    }, status=200)


@require_GET
def list_payrolls(request):
    """List all payrolls"""
    payrolls = Payroll.objects.all().order_by('-pay_date')

    result = []
    for payroll in payrolls:
        result.append({
            "email": payroll.email.email,
            "basic_salary": str(payroll.basic_salary),
            "allowances": str(payroll.allowances),
            "deductions": str(payroll.deductions),
            "bonus": str(payroll.bonus),
            "tax": str(payroll.tax),
            "net_salary": str(payroll.net_salary),
            "month": payroll.month,
            "year": payroll.year,
            "status": payroll.status,
            "pay_date": str(payroll.pay_date)
        })

    return JsonResponse({"payrolls": result}, status=200)


@require_GET
def list_tasks(request):
    tasks = TaskTable.objects.all().order_by('-created_at')
    result = []

    for task in tasks:
        result.append({
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "email": task.email.email,
            "assigned_by": task.assigned_by.email if task.assigned_by else None,
            "department": task.department,
            "priority": task.priority,
            "status": task.status,
            "start_date": str(task.start_date),
            "due_date": str(task.due_date) if task.due_date else None,
            "completed_date": str(task.completed_date) if task.completed_date else None,
            "created_at": str(task.created_at),
            "updated_at": str(task.updated_at),
        })

    return JsonResponse({"tasks": result}, status=200)


@require_GET
def get_task(request, task_id):
    try:
        task = TaskTable.objects.get(pk=task_id)
        data = {
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "email": task.email.email,
            "assigned_by": task.assigned_by.email if task.assigned_by else None,
            "department": task.department,
            "priority": task.priority,
            "status": task.status,
            "start_date": str(task.start_date),
            "due_date": str(task.due_date) if task.due_date else None,
            "completed_date": str(task.completed_date) if task.completed_date else None,
            "created_at": str(task.created_at),
            "updated_at": str(task.updated_at),
        }
        return JsonResponse(data, status=200)
    except TaskTable.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)


@csrf_exempt
@require_http_methods(["PUT"])
def update_task(request, task_id):
    try:
        task = TaskTable.objects.get(pk=task_id)
        body = json.loads(request.body)

        # update fields if provided
        for field in ['title', 'description', 'department', 'priority', 'status', 'start_date', 'due_date', 'completed_date']:
            if field in body:
                setattr(task, field, body[field])

        if 'email' in body:
            try:
                task.email = User.objects.get(email=body['email'])
            except User.DoesNotExist:
                return JsonResponse({"error": "User not found"}, status=404)

        if 'assigned_by' in body:
            try:
                task.assigned_by = User.objects.get(email=body['assigned_by'])
            except User.DoesNotExist:
                task.assigned_by = None  # optional

        task.save()
        return JsonResponse({"message": "Task updated successfully"}, status=200)
    except TaskTable.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_task(request, task_id):
    try:
        task = TaskTable.objects.get(pk=task_id)
        task.delete()
        return JsonResponse({"message": "Task deleted successfully"}, status=200)
    except TaskTable.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)
    

@csrf_exempt  # <-- Exempt CSRF
@require_POST
def create_task(request):
    """Create a new task"""
    try:
        data = json.loads(request.body)

        email = data.get("email")
        assigned_by_email = data.get("assigned_by")
        title = data.get("title")
        description = data.get("description", "")
        department = data.get("department", "")
        priority = data.get("priority", "Medium")
        status = data.get("status", "Pending")
        start_date = data.get("start_date", str(timezone.localdate()))
        due_date = data.get("due_date", None)

        # Validate required fields
        if not email or not title:
            return JsonResponse({"error": "email and title are required"}, status=400)

        # Get user objects
        user = User.objects.filter(email=email).first()
        assigned_by_user = User.objects.filter(email=assigned_by_email).first() if assigned_by_email else None

        if not user:
            return JsonResponse({"error": "User not found"}, status=404)

        # Create task
        task = TaskTable.objects.create(
            email=user,
            assigned_by=assigned_by_user,
            title=title,
            description=description,
            department=department,
            priority=priority,
            status=status,
            start_date=start_date,
            due_date=due_date
        )

        return JsonResponse({
            "message": "Task created successfully",
            "task_id": task.task_id,
            "title": task.title,
            "email": task.email.email,
            "status": task.status
        }, status=201)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer


@require_GET
def list_attendance(request):
    """List all attendance records"""
    attendance_records = Attendance.objects.all().order_by('-date')

    result = []
    for record in attendance_records:
        result.append({
            "email": record.email.email,
            "role": record.email.role,
            "fullname": record.fullname,
            "department": record.department,
            "date": str(record.date),
            "check_in": str(record.check_in) if record.check_in else None,
            "check_out": str(record.check_out) if record.check_out else None,
        })

    return JsonResponse({"attendance": result}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def create_report(request):
    try:
        data = json.loads(request.body)
        title = data.get('title')
        description = data.get('description')
        content = data.get('content')
        date_str = data.get('date')
        email_str = data.get('email')

        report_date = parse_date(date_str) if date_str else None

        if not title or not report_date or not email_str:
            return JsonResponse({"error": "Title, date, and email are required."}, status=400)

        user = User.objects.filter(email=email_str).first()
        if not user:
            return JsonResponse({"error": "User with this email not found."}, status=404)

        report = Report.objects.create(
            title=title,
            description=description,
            content=content,
            date=report_date,
            email=user
        )
        return JsonResponse({
            "id": report.id,
            "title": report.title,
            "description": report.description,
            "content": report.content,
            "date": str(report.date),
            "email": report.email.email,
            "created_at": str(report.created_at)
        }, status=201)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_http_methods(["GET"])
def list_reports(request):
    reports = Report.objects.all().order_by('-date', '-created_at')
    result = []
    for r in reports:
        result.append({
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "date": str(r.date),
            "content": r.content,
            "email": r.email.email if r.email else None,
            "created_at": r.created_at.isoformat()
        })
    return JsonResponse({"reports": result})


@csrf_exempt
@require_http_methods(["PUT"])
def update_report(request, pk):
    try:
        report = Report.objects.get(id=pk)  # No filtering by user for testing
    except Report.DoesNotExist:
        return JsonResponse({"error": "Report not found."}, status=404)

    try:
        data = json.loads(request.body)
        report.title = data.get('title', report.title)
        report.description = data.get('description', report.description)
        report.content = data.get('content', report.content)
        date_str = data.get('date')
        if date_str:
            report.date = parse_date(date_str)
        report.save()
        return JsonResponse({
            "id": report.id,
            "title": report.title,
            "description": report.description,
            "content": report.content,
            "date": str(report.date),
            "created_by": report.created_by.email if report.created_by else None,
            "created_at": str(report.created_at)
        }, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_report(request, pk):
    try:
        report = Report.objects.get(id=pk)  # No user filtering for testing
    except Report.DoesNotExist:
        return JsonResponse({"error": "Report not found."}, status=404)

    report.delete()
    return JsonResponse({"message": "Report deleted successfully."}, status=204)


@require_http_methods(["GET"])
def list_projects(request):
    projects = Project.objects.all().order_by('-created_at')
    result = [{"id": p.id, "name": p.name, "description": p.description, "status": p.status} for p in projects]
    return JsonResponse({"projects": result})


@csrf_exempt
@require_http_methods(["POST"])
def create_project(request):
    try:
        # Parse JSON body
        data = json.loads(request.body)

        # Validate owner email
        owner_email = data.get("email")
        if not owner_email:
            return JsonResponse({"error": "Owner email is required."}, status=400)
        try:
            owner_user = User.objects.get(email=owner_email)
        except User.DoesNotExist:
            return JsonResponse({"error": "User with given owner email not found."}, status=400)

        # Validate basic project data
        name = data.get("name")
        if not name:
            return JsonResponse({"error": "Project name is required."}, status=400)
        status = data.get("status", "Planning")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        description = data.get("description")

        # Create project instance (without members for now)
        project = Project.objects.create(
            name=name,
            description=description,
            status=status,
            email=owner_user,
            start_date=start_date,
            end_date=end_date,
        )

        # Handle members list
        member_emails = data.get("members", [])
        if member_emails:
            members = User.objects.filter(email__in=member_emails)
            # Check for missing emails
            missing_emails = set(member_emails) - set(members.values_list('email', flat=True))
            if missing_emails:
                return JsonResponse({
                    "error": "Some member emails not found.",
                    "missing_emails": list(missing_emails)
                }, status=400)
            # Assign members to project many-to-many field
            project.members.set(members)

        return JsonResponse({
            "message": "Project created successfully",
            "id": project.id,
            "name": project.name
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
    
@require_http_methods(["GET"])
def detail_project(request, pk):
    try:
        project = Project.objects.get(id=pk)
        return JsonResponse({"id": project.id, "name": project.name, "description": project.description, "status": project.status})
    except Project.DoesNotExist:
        return JsonResponse({"error": "Project not found"}, status=404)


@csrf_exempt
@require_http_methods(["PUT"])
def update_project(request, pk):
    try:
        project = Project.objects.get(id=pk)
        data = json.loads(request.body)
        project.name = data.get("name", project.name)
        project.description = data.get("description", project.description)
        project.status = data.get("status", project.status)
        project.save()
        return JsonResponse({"message": "Project updated"})
    except Project.DoesNotExist:
        return JsonResponse({"error": "Project not found"}, status=404)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_project(request, pk):
    try:
        project = Project.objects.get(id=pk)
        project.delete()
        return JsonResponse({"message": "Project deleted"})
    except Project.DoesNotExist:
        return JsonResponse({"error": "Project not found"}, status=404)
    

@require_http_methods(["GET"])
def list_notices(request):
    notices = Notice.objects.all().order_by('-posted_date')
    result = []
    for notice in notices:
        result.append({
            "id": notice.id,
            "title": notice.title,
            "message": notice.message,
            "email": notice.email.email if notice.email else None,
            "notice_by": notice.notice_by.email if notice.notice_by else None,
            "notice_to": notice.notice_to.email if notice.notice_to else None,
            "posted_date": notice.posted_date.isoformat(),
            "valid_until": notice.valid_until.isoformat() if notice.valid_until else None,
            "important": notice.important,
            "attachment": notice.attachment.url if notice.attachment else None,
        })
    return JsonResponse({"notices": result})


@csrf_exempt
@require_http_methods(["POST"])
def create_notice(request):
    try:
        data = json.loads(request.body)
        email_user = User.objects.filter(email=data.get("email")).first() if data.get("email") else None
        notice_by_user = User.objects.filter(email=data.get("notice_by")).first() if data.get("notice_by") else None
        notice_to_user = User.objects.filter(email=data.get("notice_to")).first() if data.get("notice_to") else None
        notice = Notice.objects.create(
            title=data.get("title"),
            message=data.get("message"),
            email=email_user,
            notice_by=notice_by_user,
            notice_to=notice_to_user,
            important=data.get("important", False),
        )
        return JsonResponse({
            "id": notice.id,
            "title": notice.title,
            "notice_by": notice.notice_by.email if notice.notice_by else None,
            "notice_to": notice.notice_to.email if notice.notice_to else None,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_http_methods(["GET"])
def detail_notice(request, pk):
    try:
        notice = Notice.objects.get(id=pk)
        return JsonResponse({
            "id": notice.id,
            "title": notice.title,
            "message": notice.message,
            "email": notice.email.email if notice.email else None,
            "notice_by": notice.notice_by.email if notice.notice_by else None,
            "notice_to": notice.notice_to.email if notice.notice_to else None,
            "posted_date": notice.posted_date.isoformat(),
            "valid_until": notice.valid_until.isoformat() if notice.valid_until else None,
            "important": notice.important,
            "attachment": notice.attachment.url if notice.attachment else None,
        })
    except Notice.DoesNotExist:
        return JsonResponse({"error": "Notice not found"}, status=404)


@csrf_exempt
@require_http_methods(["PUT"])
def update_notice(request, pk):
    try:
        notice = Notice.objects.get(id=pk)
        data = json.loads(request.body)
        notice.title = data.get("title", notice.title)
        notice.message = data.get("message", notice.message)
        notice.important = data.get("important", notice.important)
        if data.get("notice_by"):
            notice.notice_by = User.objects.filter(email=data.get("notice_by")).first()
        if data.get("notice_to"):
            notice.notice_to = User.objects.filter(email=data.get("notice_to")).first()

        notice.save()
        return JsonResponse({"message": "Notice updated"})
    except Notice.DoesNotExist:
        return JsonResponse({"error": "Notice not found"}, status=404)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_notice(request, pk):
    try:
        notice = Notice.objects.get(id=pk)
        notice.delete()
        return JsonResponse({"message": "Notice deleted"})
    except Notice.DoesNotExist:
        return JsonResponse({"error": "Notice not found"}, status=404)
    

@api_view(['GET'])
def get_employee_by_email(request, email):
    try:
        employee = Employee.objects.get(email=email)
        return JsonResponse({
            "email": employee.email.email,
            "fullname": employee.fullname,
            "profile_picture": employee.profile_picture.url if employee.profile_picture else "",
        })
    except Employee.DoesNotExist:
        return JsonResponse({"error": "Employee not found"}, status=404)


def health_check(request):
    return JsonResponse({"status": "ok"})


@require_GET
def get_tasks_by_assigned_by(request, assigned_by_email):
    try:
        tasks = TaskTable.objects.filter(assigned_by__email=assigned_by_email)
        if not tasks.exists():
            return JsonResponse({"error": "No tasks found for this assigned_by email"}, status=404)
        
        data = []
        for task in tasks:
            data.append({
                "task_id": task.task_id,
                "title": task.title,
                "description": task.description,
                "email": task.email.email,
                "assigned_by": task.assigned_by.email if task.assigned_by else None,
                "department": task.department,
                "priority": task.priority,
                "status": task.status,
                "start_date": str(task.start_date),
                "due_date": str(task.due_date) if task.due_date else None,
                "completed_date": str(task.completed_date) if task.completed_date else None,
                "created_at": str(task.created_at),
                "updated_at": str(task.updated_at),
            })
        
        return JsonResponse(data, safe=False, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

@csrf_exempt
def create_document(request):
    if request.method == "POST":
        email = request.POST.get("email")
        user = get_object_or_404(User, email=email)

        # Use email prefix as folder name
        folder_name = email.split("@")[0].lower()

        client = boto3.client(
            's3',
            endpoint_url='http://194.238.19.109:9000',
            aws_access_key_id='djangouser',
            aws_secret_access_key='django_secret_key',
        )
        bucket_name = 'hrms-media'
        base_url = f"http://194.238.19.109:9000/{bucket_name}/"
        uploaded_files = {}

        document_fields = [
            "tenth", "twelth", "degree", "masters", "marks_card", "certificates",
            "award", "resume", "id_proof", "appointment_letter", "offer_letter",
            "releaving_letter", "resignation_letter", "achievement_crt", "bonafide_crt"
        ]

        for field in document_fields:
            file_obj = request.FILES.get(field)
            if file_obj:
                ext = file_obj.name.split('.')[-1]  # file extension
                key = f"documents/{folder_name}/{field}.{ext}"  # fixed file name
                client.upload_fileobj(file_obj, bucket_name, key)
                uploaded_files[field] = f"{base_url}{key}"

        # Create new Document
        document = Document.objects.create(
            email=user,
            **{field: uploaded_files.get(field) for field in document_fields}
        )

        return JsonResponse({
            "message": "Document created successfully",
            "id": document.id,
            "urls": uploaded_files
        })


@csrf_exempt
def update_document(request, email):
    if request.method in ["POST", "PATCH"]:
        user = get_object_or_404(User, email=email)
        doc = Document.objects.filter(email=user).last()
        if not doc:
            # If no document exists, create new one
            doc = Document.objects.create(email=user)

        # Folder name = email prefix
        folder_name = email.split("@")[0].lower()

        client = boto3.client(
            's3',
            endpoint_url='http://194.238.19.109:9000',
            aws_access_key_id='djangouser',
            aws_secret_access_key='django_secret_key',
        )
        bucket_name = 'hrms-media'
        base_url = f"http://194.238.19.109:9000/{bucket_name}/"

        document_fields = [
            "tenth", "twelth", "degree", "masters", "marks_card", "certificates",
            "award", "resume", "id_proof", "appointment_letter", "offer_letter",
            "releaving_letter", "resignation_letter", "achievement_crt", "bonafide_crt"
        ]

        for field in document_fields:
            file_obj = request.FILES.get(field)
            if file_obj:
                ext = file_obj.name.split('.')[-1]
                key = f"documents/{folder_name}/{field}.{ext}"

                # Delete old file if exists
                old_file_url = getattr(doc, field)
                if old_file_url and old_file_url.startswith(base_url):
                    old_key = old_file_url.replace(base_url, "")
                    try:
                        client.delete_object(Bucket=bucket_name, Key=old_key)
                    except Exception as e:
                        print(f"Failed to delete old file {old_key}: {e}")

                # Upload new file
                client.upload_fileobj(file_obj, bucket_name, key)
                setattr(doc, field, f"{base_url}{key}")

        doc.save()
        return JsonResponse({"message": "Document updated successfully"})


@csrf_exempt
def delete_document(request, email):
    if request.method == "DELETE":
        user = get_object_or_404(User, email=email)
        documents = Document.objects.filter(email=user)
        count = documents.count()
        documents.delete()
        return JsonResponse({"message": f"{count} document(s) deleted successfully"})


@csrf_exempt
def list_documents(request):
    documents = Document.objects.all()
    data = []

    for doc in documents:
        doc_data = {"id": doc.id, "email": doc.email.email}
        for field in doc._meta.get_fields():
            if field.name in ["id", "email", "uploaded_at"]:
                continue
            file_value = getattr(doc, field.name)
            doc_data[field.name] = file_value if file_value else None
        data.append(doc_data)

    return JsonResponse(data, safe=False)


@csrf_exempt
def get_document(request, email):
    user = get_object_or_404(User, email=email)
    documents = Document.objects.filter(email=user)
    if not documents.exists():
        return JsonResponse({"message": "No documents found"}, status=404)

    data = []
    for doc in documents:
        doc_data = {"email": user.email}
        for field in doc._meta.get_fields():
            if field.name in ["id", "email", "uploaded_at"]:
                continue
            file_value = getattr(doc, field.name)
            doc_data[field.name] = file_value if file_value else None
        data.append(doc_data)

    return JsonResponse(data, safe=False)


@csrf_exempt
def create_award(request):
    if request.method == "POST":
        data = request.POST
        email = data.get("email")
        user = get_object_or_404(User, email=email)
        award = Award.objects.create(
            email=user,
            title=data.get("title"),
            description=data.get("description"),
            date=data.get("date"),
            photo=request.FILES.get("photo"),
        )
        return JsonResponse({"message": "Award created", "id": award.id})


def list_awards(request):
    awards = Award.objects.all()
    data = []
    for a in awards:
        data.append({
            "id": a.id,
            "email": a.email.email,
            "title": a.title,
            "description": a.description,
            "date": a.date,
            "photo": a.photo.url if a.photo else None,
        })
    return JsonResponse(data, safe=False)


def get_award(request, id):
    a = get_object_or_404(Award, id=id)
    data = {
        "id": a.id,
        "email": a.email.email,
        "title": a.title,
        "description": a.description,
        "date": a.date,
        "photo": a.photo.url if a.photo else None,
    }
    return JsonResponse(data)


@csrf_exempt
def update_award(request, id):
    if request.method in ["POST", "PATCH"]:
        a = get_object_or_404(Award, id=id)
        data = request.POST
        for field in ["title", "description", "date"]:
            if data.get(field):
                setattr(a, field, data.get(field))
        if request.FILES.get("photo"):
            a.photo = request.FILES.get("photo")
        a.save()
        return JsonResponse({"message": "Award updated"})


@csrf_exempt
def delete_award(request, id):
    if request.method == "DELETE":
        a = get_object_or_404(Award, id=id)
        a.delete()
        return JsonResponse({"message": "Award deleted"})


# Attendance HTML page
def attendance_page(request):
    return render(request, 'attendance.html')


OFFICE_LAT = 13.068906816007116
OFFICE_LON = 77.55541294505542
LOCATION_RADIUS_METERS = 500  # 100m allowed radius
IST = pytz.timezone("Asia/Kolkata")


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_attendance_view(request):
    try:
        # 1️⃣ Get latitude and longitude from POST request
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")

        if latitude is None or longitude is None:
            return JsonResponse({"status": "fail", "message": "Latitude and longitude required"}, status=400)

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return JsonResponse({"status": "fail", "message": "Invalid latitude or longitude"}, status=400)

        # 2️⃣ Get uploaded image
        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return JsonResponse({"status": "fail", "message": "No image provided"}, status=400)

        # Save temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        uploaded_img = face_recognition.load_image_file(tmp_path)
        uploaded_encodings = face_recognition.face_encodings(uploaded_img)

        if not uploaded_encodings:
            os.remove(tmp_path)
            return JsonResponse({"status": "fail", "message": "No face detected"}, status=400)

        uploaded_encoding = uploaded_encodings[0]

        # 3️⃣ Loop through employees and check face match
        employees = Employee.objects.all()
        for emp in employees:
            if not emp.profile_picture or not os.path.exists(emp.profile_picture.path):
                continue

            emp_img = face_recognition.load_image_file(emp.profile_picture.path)
            emp_encodings = face_recognition.face_encodings(emp_img)
            if not emp_encodings:
                continue

            emp_encoding = emp_encodings[0]
            match = face_recognition.compare_faces([emp_encoding], uploaded_encoding, tolerance=0.5)

            if match[0]:
                # ✅ Check if within 100m of office
                user_location = (latitude, longitude)
                office_location = (OFFICE_LAT, OFFICE_LON)
                distance_meters = geodesic(user_location, office_location).meters

                if distance_meters > LOCATION_RADIUS_METERS:
                    os.remove(tmp_path)
                    return JsonResponse({
                        "status": "fail",
                        "message": f"User too far from office ({distance_meters:.2f} meters). Attendance denied."
                    }, status=400)

                # ✅ Mark attendance
                now_ist = timezone.localtime(timezone.now(), IST)
                today = now_ist.date()
                now_time = now_ist.time()

                obj, created = Attendance.objects.get_or_create(
                    email=emp.email,
                    date=today,
                    defaults={
                        "check_in": now_time,
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_verified": True
                    }
                )

                if created:
                    msg = f"Check-in marked for {emp.fullname}"
                else:
                    if obj.check_out:
                        msg = f"Attendance already marked for today ({emp.fullname})"
                    else:
                        obj.check_out = now_time
                        obj.latitude = latitude
                        obj.longitude = longitude
                        obj.location_verified = True
                        obj.save()
                        msg = f"Check-out marked for {emp.fullname}"

                os.remove(tmp_path)
                return JsonResponse({"status": "success", "message": msg})

        os.remove(tmp_path)
        return JsonResponse({"status": "fail", "message": "No match found"}, status=404)

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


token_generator = PasswordResetTokenGenerator()

class RequestPasswordResetView(APIView):
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'No account found with this email'}, status=status.HTTP_404_NOT_FOUND)

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{uidb64}/{token}/"

        # Render HTML template
        html_message = render_to_string('emails/password_reset.html', {
            'reset_link': reset_link,
            'current_year': datetime.now().year
        })

        # Plain text version
        plain_message = f"""
            Password Reset Request

            Hello,

            We received a request to reset your password. Click the link below to create a new password:

            {reset_link}

            This link will expire in 24 hours for security reasons.

            If you didn't request a password reset, please ignore this email.

            Best regards,
            Your Company Name
        """

        send_mail(
            subject='Password Reset Request',
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        return Response({'message': 'Password reset link sent successfully'}, status=status.HTTP_200_OK)

class PasswordResetConfirmView(APIView):
    def post(self, request, uidb64, token):
        password = request.data.get('password')
        if not password:
            return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Invalid reset link'}, status=status.HTTP_400_BAD_REQUEST)

        if not token_generator.check_token(user, token):
            return Response({'error': 'Token is invalid or expired'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save()
        return Response({'message': 'Password has been reset successfully'}, status=status.HTTP_200_OK)

