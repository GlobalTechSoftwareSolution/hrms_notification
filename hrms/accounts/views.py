import os, json, pytz, face_recognition, tempfile, requests, boto3, mimetypes

from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, time
from geopy.distance import geodesic
from xhtml2pdf import pisa
from threading import Thread

from django.conf import settings
from django.utils import timezone
from django.http import Http404, JsonResponse, HttpResponse
from accounts.models import Document
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth import authenticate, get_user_model
from django.utils.dateparse import parse_date
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.decorators import method_decorator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail, EmailMessage
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.db.models import Q 
from django.db import models, IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.http.multipartparser import MultiPartParser, MultiPartParserError

from rest_framework import status, viewsets, generics, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes, action

# Models
from .models import (
    User, CEO, HR, Manager, Department, Employee, Attendance, Admin,
    Leave, Payroll, TaskTable, Project, Notice, Report,
    Document, Award, Ticket, EmployeeDetails, ReleavedEmployee, Holiday, AbsentEmployeeDetails, AppliedJobs, 
    JobPosting
)

# Serializers
from .serializers import (
    UserSerializer, CEOSerializer, HRSerializer, ManagerSerializer, DepartmentSerializer,
    EmployeeSerializer, SuperUserCreateSerializer, UserRegistrationSerializer, ProjectSerializer,
    AdminSerializer, ReportSerializer, RegisterSerializer, DocumentSerializer, AwardSerializer, TicketSerializer, EmployeeDetailsSerializer, HolidaySerializer, AbsentEmployeeDetailsSerializer, CareerSerializer, AppliedJobSerializer, ReleavedEmployeeSerializer
)

# Ensure User model points to custom one
User = get_user_model()

# Constants
OFFICE_LAT = 13.068906816007116
OFFICE_LON = 77.55541294505542
LOCATION_RADIUS_METERS = 100  # 100m allowed radius
IST = pytz.timezone("Asia/Kolkata")


def verify_location(latitude, longitude, radius_meters=None):
    """Verify if user is within allowed radius of office"""
    if radius_meters is None:
        radius_meters = LOCATION_RADIUS_METERS
    
    user_location = (latitude, longitude)
    office_location = (OFFICE_LAT, OFFICE_LON)
    distance_meters = geodesic(user_location, office_location).meters
    
    return distance_meters <= radius_meters, distance_meters


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

CHECK_IN_DEADLINE = time(10, 45)  # 10:45 AM

def mark_attendance_by_email(email_str, latitude=None, longitude=None):
    """
    Marks attendance for a user based on email and live location.
    Only works if user is within 100 meters of the office.
    Automatically marks absent if no check-in before 10:45 AM.
    """
    if not is_email_exists(email_str):
        print(f"[mark_attendance_by_email] Email {email_str} not found. Attendance not marked.")
        return None

    if latitude is None or longitude is None:
        print("[mark_attendance_by_email] Location not provided — attendance not marked.")
        return None

    is_within_radius, distance_meters = verify_location(latitude, longitude)
    
    if not is_within_radius:
        print(f"[mark_attendance_by_email] User {email_str} is too far ({distance_meters:.2f}m). Attendance denied.")
        return None

    today = timezone.localdate()
    now = timezone.now().astimezone(IST)
    current_time = now.time()
    print(f"[mark_attendance_by_email] Processing attendance for {email_str} on {today} at {now}")

    try:
        user_instance = User.objects.get(email=email_str)
    except User.DoesNotExist:
        print(f"[mark_attendance_by_email] User instance not found for {email_str}")
        return None

    # ------------------- Check for existing attendance ------------------- #
    attendance_exists = Attendance.objects.filter(email=user_instance, date=today).exists()

    # ------------------- Automatically mark absent if past 10:45 and no check-in ------------------- #
    if current_time > CHECK_IN_DEADLINE and not attendance_exists:
        absent_entry, created = AbsentEmployeeDetails.objects.get_or_create(
            email=user_instance,
            date=today
        )
        if created:
            print(f"[mark_attendance_by_email] {email_str} did not check in before 10:45 AM. Marked as absent.")
        return None  # Do not allow late check-in

    # ------------------- Existing Attendance Logic ------------------- #
    try:
        attendance = Attendance.objects.get(email=user_instance, date=today)
        if attendance.check_out is None:
            attendance.check_out = current_time
            attendance.save()
            print(f"[mark_attendance_by_email] Updated check_out for {email_str} at {now}")
    except Attendance.DoesNotExist:
        try:
            attendance = Attendance.objects.create(
                email=user_instance,
                date=today,
                check_in=current_time,
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

        # Get instance in the given model (Employee, Manager, etc.)
        instance = ModelClass.objects.get(email=email)

        # Delete associated image from MinIO if exists
        client = get_s3_client()
        bucket_name = "hrms-media"
        base_url = getattr(settings, "BASE_BUCKET_URL", f"https://minio.globaltechsoftwaresolutions.cloud/browser/hrms-media/")

        if hasattr(instance, "profile_picture") and instance.profile_picture:
            file_url = instance.profile_picture
            if file_url.startswith(base_url):
                key = file_url.replace(base_url, "")
                try:
                    client.delete_object(Bucket=bucket_name, Key=key)
                    print(f"Deleted file from MinIO: {key}")
                except Exception as e:
                    print(f"Failed to delete file {key}: {e}")

        # Delete instance from role table
        instance.delete()
        print(f"Deleted {ModelClass.__name__} record with email {email}")

        # Delete corresponding User record
        from accounts.models import User
        try:
            user = User.objects.get(email=email)
            user.delete()
            print(f"Deleted User record with email {email}")
        except User.DoesNotExist:
            print(f"No User record found to delete for email {email}")

        return JsonResponse({
            "message": f"{ModelClass.__name__} and User deleted successfully"
        })
    except ModelClass.DoesNotExist:
        return JsonResponse({"error": f"{ModelClass.__name__} not found"}, status=404)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    lookup_field = 'email'

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return UserRegistrationSerializer
        return UserSerializer

# ------------------- S3 Client -------------------
# ------------------- MinIO Client -------------------

import json
import boto3
from django.conf import settings
from rest_framework import viewsets
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from .models import Employee, EmployeeDetails, HR, Manager, Admin, CEO
from .serializers import EmployeeSerializer, HRSerializer, ManagerSerializer, AdminSerializer, CEOSerializer

User = get_user_model()

# ------------------- MinIO Client -------------------
def get_s3_client():
    minio_conf = getattr(settings, "MINIO_STORAGE", {
        "ENDPOINT": "minio.globaltechsoftwaresolutions.cloud",
        "ACCESS_KEY": "admin",
        "SECRET_KEY": "admin12345",
        "BUCKET_NAME": "hrms-media",
        "USE_SSL": True,
    })
    protocol = "https" if minio_conf.get("USE_SSL", False) else "http"
    client = boto3.client(
        "s3",
        endpoint_url=f"{protocol}://{minio_conf['ENDPOINT']}",
        aws_access_key_id=minio_conf["ACCESS_KEY"],
        aws_secret_access_key=minio_conf["SECRET_KEY"],
        verify=True  # Use True for SSL verification
    )
    return client

BASE_BUCKET_URL = getattr(settings, "BASE_BUCKET_URL", "https://minio.globaltechsoftwaresolutions.cloud/hrms-media/")
BUCKET_NAME = settings.MINIO_STORAGE["BUCKET_NAME"]

# ------------------- Base ViewSet -------------------
class BaseUserViewSet(viewsets.ModelViewSet):
    lookup_field = "email"

    def _upload_profile_picture(self, instance, file_obj):
        client = get_s3_client()
        ext = file_obj.name.split('.')[-1]

        # ✅ Get plain email string (handle both User object and string)
        email_str = (
            instance.email.email
            if hasattr(instance.email, "email") else instance.email
        )

        # ✅ Generate correct S3 key
        key = f'images/{email_str}/profile_picture.{ext}'

        # Delete old picture
        if hasattr(instance, "profile_picture") and instance.profile_picture and instance.profile_picture != f"{BASE_BUCKET_URL}{key}":
            old_key = instance.profile_picture.replace(BASE_BUCKET_URL, "")
            try:
                client.delete_object(Bucket=BUCKET_NAME, Key=old_key)
            except Exception as e:
                print(f"Failed to delete old picture: {e}")

        # Upload new picture
        client.upload_fileobj(file_obj, BUCKET_NAME, key, ExtraArgs={"ContentType": file_obj.content_type})
        instance.profile_picture = f"{BASE_BUCKET_URL}{key}"
        instance.save()


    def _update_employee_details(self, instance, data):
        details_fields = [
            'account_number', 'father_name', 'father_contact', 'mother_name', 'mother_contact',
            'wife_name', 'home_address', 'total_siblings', 'brothers',
            'sisters', 'total_children', 'bank_name', 'branch', 'pf_no',
            'pf_uan', 'ifsc'
        ]
        details_data = {f: data.get(f) for f in details_fields if data.get(f) is not None}
        if details_data:
            details, _ = EmployeeDetails.objects.get_or_create(email=instance.email)
            for field, value in details_data.items():
                setattr(details, field, value)
            details.save()

    # ---------- CREATE ----------
    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        profile_file = request.FILES.get('profile_picture')
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        if profile_file:
            self._upload_profile_picture(instance, profile_file)

        # Update related EmployeeDetails if applicable
        if hasattr(instance, "email"):
            self._update_employee_details(instance, data)

        return Response(self.get_serializer(instance).data, status=201)

    # ---------- PARTIAL UPDATE ----------
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        updated = False

        # Profile picture
        if 'profile_picture' in request.FILES:
            self._upload_profile_picture(instance, request.FILES['profile_picture'])
            updated = True

        # Update main model fields
        for field, value in request.data.items():
            if hasattr(instance, field) and field != 'profile_picture':
                field_obj = instance._meta.get_field(field)
                
                # Handle ForeignKey fields
                if field_obj.is_relation and isinstance(field_obj, models.ForeignKey):
                    related_model = field_obj.remote_field.model

                    try:
                        # Assume value is an email or PK
                        related_instance = related_model.objects.get(email=value)
                        setattr(instance, field, related_instance)
                        updated = True
                    except related_model.DoesNotExist:
                        return Response(
                            {"error": f"{related_model.__name__} with email '{value}' does not exist"},
                            status=400
                        )
                else:
                    setattr(instance, field, value)
                    updated = True

        if updated:
            instance.save()

        # Update related EmployeeDetails if applicable
        if hasattr(instance, "email"):
            self._update_employee_details(instance, request.data)

        return Response(self.get_serializer(instance).data, status=200)


    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # ---------- DESTROY ----------
    def destroy(self, request, email=None):
        try:
            # 1️⃣ Fetch employee
            employee = get_object_or_404(Employee, email=email)

            # 2️⃣ Extract plain email string
            if hasattr(employee.email, "email"):  # ForeignKey(User)
                email_str = employee.email.email
            else:
                email_str = employee.email

            # 3️⃣ Create ReleavedEmployee entry with plain email
            # ReleavedEmployee.objects.create(
            #     email=email_str,
            #     fullname=getattr(employee, "fullname", None),
            #     phone=getattr(employee, "phone", None),
            #     designation=getattr(employee, "designation", None),
            #     role="employee"  # explicitly set which table they came from
            # )

            # 4️⃣ Delete related EmployeeDetails
            try:
                user_obj = User.objects.filter(email=email_str).first()
                if user_obj:
                    EmployeeDetails.objects.filter(email=user_obj).delete()
            except Exception as e:
                print(f"[WARN] Error deleting EmployeeDetails: {e}")

            # 5️⃣ Delete profile picture from MinIO
            if hasattr(employee, "profile_picture") and employee.profile_picture:
                client = get_s3_client()
                key = employee.profile_picture.replace(BASE_BUCKET_URL, "")
                try:
                    client.delete_object(Bucket=BUCKET_NAME, Key=key)
                except Exception as e:
                    print(f"[WARN] Failed to delete profile picture from MinIO: {e}")

            # 6️⃣ Delete main Employee and related User safely
            employee.delete()
            user = User.objects.filter(email=email_str).first()
            if user:
                user.delete()

            return Response(
                {"message": f"{email_str} successfully offboarded."},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ---------- RETRIEVE ----------
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_data = self.get_serializer(instance).data

        # Fetch EmployeeDetails via User
        user = getattr(instance, 'email', None)  # Employee.email is a FK to User
        if user:
            try:
                details = EmployeeDetails.objects.get(email=user)
                for field in details._meta.fields:
                    if field.name not in ['id', 'email']:
                        instance_data[field.name] = getattr(details, field.name)
            except EmployeeDetails.DoesNotExist:
                pass

        return Response(instance_data)


    # ---------- LIST ----------
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        data = []
        for instance in queryset:
            instance_data = self.get_serializer(instance).data
            user = getattr(instance, 'email', None)
            if user:
                try:
                    details = EmployeeDetails.objects.get(email=user)
                    for field in details._meta.fields:
                        if field.name not in ['id', 'email']:
                            instance_data[field.name] = getattr(details, field.name)
                except EmployeeDetails.DoesNotExist:
                    pass
            data.append(instance_data)
        return Response(data)



# ------------------- Role-specific ViewSets -------------------
class EmployeeViewSet(BaseUserViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer


class HRViewSet(BaseUserViewSet):
    queryset = HR.objects.all()
    serializer_class = HRSerializer


class ManagerViewSet(BaseUserViewSet):
    queryset = Manager.objects.all()
    serializer_class = ManagerSerializer


class AdminViewSet(BaseUserViewSet):
    queryset = Admin.objects.all()
    serializer_class = AdminSerializer


class CEOViewSet(BaseUserViewSet):
    queryset = CEO.objects.all()
    serializer_class = CEOSerializer


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    lookup_field = 'email'  # use email instead of pk

class AwardViewSet(viewsets.ModelViewSet):
    queryset = Award.objects.all()
    serializer_class = AwardSerializer
    lookup_field = 'email'  # use email instead of pk
    
class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    lookup_field = 'id'

class ReleavedEmployeeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ReleavedEmployee - archived/offboarded employees.
    - List all released employees
    - Retrieve by email (string field, not FK)
    - Update approval status
    """
    queryset = ReleavedEmployee.objects.all().order_by('-offboarded_at')
    serializer_class = ReleavedEmployeeSerializer
    lookup_field = 'email'  # Use email string as lookup
    
    def get_object(self):
        """
        Override to lookup by email string field.
        """
        email = self.kwargs.get('email')
        obj = get_object_or_404(ReleavedEmployee, email=email)
        return obj

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
            Q(start_date__lte=new_end) & Q(end_date__gte=new_start)
        ).exists()

        if overlapping_leave_exists:
            return JsonResponse({"error": "You already have a leave request overlapping requested dates."}, status=400)

        leave = Leave.objects.create(
            email=user,
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

        # Create new payroll entry
        payroll = Payroll.objects.create(
            email=user,
            basic_salary=data.get("basic_salary", 0.00),
            month=month,
            year=year,
            status=data.get("status", "Pending"),
            STD=data.get("STD", 0),
            LOP=data.get("LOP", 0),
        )

        return JsonResponse({
            "message": "Payroll created successfully",
            "payroll": {
                "email": payroll.email.email,
                "basic_salary": str(payroll.basic_salary),
                "STD": payroll.STD,
                "LOP": payroll.LOP,
                "month": payroll.month,
                "year": payroll.year,
                "status": payroll.status,
                "pay_date": str(payroll.pay_date),
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

        # Optional: Allow updating STD and LOP when status changes
        payroll.STD = data.get("STD", payroll.STD)
        payroll.LOP = data.get("LOP", payroll.LOP)
        payroll.status = new_status
        payroll.save()

        return JsonResponse({
            "message": f"Payroll status updated to {new_status}",
            "payroll": {
                "email": payroll.email.email,
                "basic_salary": str(payroll.basic_salary),
                "STD": payroll.STD,
                "LOP": payroll.LOP,
                "month": payroll.month,
                "year": payroll.year,
                "status": payroll.status,
                "pay_date": str(payroll.pay_date),
            }
        }, status=200)

    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll record not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def get_payroll(request, email):
    """Fetch all payroll details for an employee"""
    if request.method != "GET":
        return JsonResponse({"error": "Only GET method allowed"}, status=405)

    user = get_object_or_404(User, email=email)
    payrolls = Payroll.objects.filter(email=user).order_by('-year', '-month')

    payroll_list = []
    for payroll in payrolls:
        payroll_list.append({
            "email": payroll.email.email,
            "basic_salary": str(payroll.basic_salary),
            "STD": payroll.STD,
            "LOP": payroll.LOP,
            "month": payroll.month,
            "year": payroll.year,
            "status": payroll.status,
            "pay_date": str(payroll.pay_date),
        })

    return JsonResponse({"payrolls": payroll_list}, status=200)


@require_GET
def list_payrolls(request):
    """List all payrolls"""
    payrolls = Payroll.objects.all().order_by('-pay_date')

    result = []
    for payroll in payrolls:
        result.append({
            "email": payroll.email.email,
            "basic_salary": str(payroll.basic_salary),
            "STD": payroll.STD,
            "LOP": payroll.LOP,
            "month": payroll.month,
            "year": payroll.year,
            "status": payroll.status,
            "pay_date": str(payroll.pay_date),
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
@require_http_methods(["PATCH"])
def update_task(request, task_id):
    try:
        task = TaskTable.objects.get(pk=task_id)
        body = json.loads(request.body)

        # update fields if provided
        for field in ['title', 'description', 'priority', 'status', 'start_date', 'due_date', 'completed_date']:
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


@require_GET
def get_attendance(request, email):
    """Get attendance records for a specific email"""
    user = get_object_or_404(User, email=email)
    attendance_records = Attendance.objects.filter(email=user).order_by('-date')

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
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat()
        })
    return JsonResponse({"reports": result})


@csrf_exempt
@require_http_methods(["PATCH"])
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
            "created_at": str(report.created_at),
            "updated_at": str(report.updated_at)
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


@api_view(['GET'])
def list_projects(request):
    projects = Project.objects.all().order_by('-created_at')
    serializer = ProjectSerializer(projects, many=True)
    return Response({"projects": serializer.data}, status=status.HTTP_200_OK)


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
    
    
@api_view(['GET'])
def get_project(request, pk):
    try:
        project = Project.objects.get(id=pk)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = ProjectSerializer(project)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ---------- Update Project ----------
@api_view(['PATCH'])
def update_project(request, pk):
    try:
        project = Project.objects.get(id=pk)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = ProjectSerializer(project, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Project updated successfully", "project": serializer.data}, status=status.HTTP_200_OK)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
@require_http_methods(["PATCH"])
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
    

import boto3
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.http.multipartparser import MultiPartParser, MultiPartParserError
from .models import Document, User  # adjust import if needed



DOCUMENT_FIELDS = [
    "tenth", "twelth", "degree", "masters", "marks_card", "certificates",
    "award", "resume", "id_proof", "appointment_letter", "offer_letter",
    "releaving_letter", "resignation_letter", "achievement_crt", "bonafide_crt",
]

# Use BASE_BUCKET_URL from settings.py
BASE_BUCKET_URL = getattr(settings, "BASE_BUCKET_URL", "https://minio.globaltechsoftwaresolutions.cloud/browser/hrms-media/")

@csrf_exempt
def create_document(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    email = request.POST.get("email")
    if not email:
        return JsonResponse({"error": "Email is required"}, status=400)

    user = get_object_or_404(User, email=email)
    folder_name = email.split("@")[0].lower()
    client = get_s3_client()
    bucket_name = settings.MINIO_STORAGE["BUCKET_NAME"]
    uploaded_files = {}

    for field in DOCUMENT_FIELDS:
        file_obj = request.FILES.get(field)
        if file_obj:
            ext = file_obj.name.split(".")[-1]
            key = f"documents/{folder_name}/{field}.{ext}"
            client.upload_fileobj(file_obj, bucket_name, key, ExtraArgs={"ACL": "public-read"})
            uploaded_files[field] = f"{BASE_BUCKET_URL}{key}"

    document = Document.objects.create(
        email=user,
        **{field: uploaded_files.get(field) for field in DOCUMENT_FIELDS}
    )

    return JsonResponse({
        "message": "Document created successfully",
        "id": document.id,
        "urls": uploaded_files
    })

# UPDATE Document
@csrf_exempt
def update_document(request, email):
    if request.method != "PATCH":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user = get_object_or_404(User, email=email)

    # Parse multipart form-data manually for PATCH
    try:
        parser = MultiPartParser(request.META, request, request.upload_handlers, request.encoding)
        data, files = parser.parse()
    except MultiPartParserError as e:
        return JsonResponse({"error": f"Failed to parse multipart data: {e}"}, status=400)

    # Get or create document record
    doc, _ = Document.objects.get_or_create(email=user)
    Document.objects.filter(email=user).exclude(id=doc.id).delete()

    folder_name = email.split("@")[0].lower()
    client = get_s3_client()
    bucket_name = "hrms-media"
    updated_files = {}

    for field in DOCUMENT_FIELDS:
        file_obj = files.get(field)
        if not file_obj:
            continue

        # ✅ Use fixed key name for this field to overwrite
        key = f"documents/{folder_name}/{field}{file_obj.name[file_obj.name.rfind('.'):]}"  # preserve new extension

        # Optionally delete old file if the extension changed
        old_file_url = getattr(doc, field)
        if old_file_url and old_file_url != f"{BASE_BUCKET_URL}{key}":
            old_key = old_file_url.replace(BASE_BUCKET_URL, "")
            try:
                client.delete_object(Bucket=bucket_name, Key=old_key)
                print(f"Deleted old file: {old_key}")
            except Exception as e:
                print(f"Failed to delete old file {old_key}: {e}")

        # Upload new file (will replace if key exists)
        try:
            client.upload_fileobj(file_obj, bucket_name, key, ExtraArgs={"ACL": "public-read"})
            new_url = f"{BASE_BUCKET_URL}{key}"
            setattr(doc, field, new_url)
            updated_files[field] = new_url
        except Exception as e:
            return JsonResponse({"error": f"Upload failed for {field}: {str(e)}"}, status=500)

    if updated_files:
        doc.save()
        return JsonResponse({"message": "Document(s) updated successfully", "updated_files": updated_files})
    else:
        return JsonResponse({"message": "No files uploaded"}, status=400)



# DELETE Document
@csrf_exempt
def delete_document(request, email):
    if request.method != "DELETE":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user = get_object_or_404(User, email=email)
    documents = Document.objects.filter(email=user)
    if not documents.exists():
        return JsonResponse({"message": "No documents found for this user"}, status=404)

    client = get_s3_client()
    bucket_name = "hrms-media"
    deleted_files = []

    for doc in documents:
        folder_name = email.split("@")[0].lower()
        prefix = f"documents/{folder_name}/"

        # Delete all objects under this folder
        response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        if "Contents" in response:
            for obj in response["Contents"]:
                try:
                    client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                    deleted_files.append(obj["Key"])
                except Exception as e:
                    print(f"Failed to delete {obj['Key']}: {e}")

        doc.delete()

    return JsonResponse({
        "message": f"{len(deleted_files)} file(s) and document record(s) deleted successfully",
        "deleted_files": deleted_files
    })


# LIST All Documents
@csrf_exempt
def list_documents(request):
    documents = Document.objects.all()
    data = []

    for doc in documents:
        doc_data = {"id": doc.id, "email": doc.email.email}
        for field in DOCUMENT_FIELDS:
            doc_data[field] = getattr(doc, field) if getattr(doc, field) else None
        data.append(doc_data)

    return JsonResponse(data, safe=False)


# GET Document for a user
@csrf_exempt
def get_document(request, email):
    user = get_object_or_404(User, email=email)
    documents = Document.objects.filter(email=user)
    if not documents.exists():
        return JsonResponse({"message": "No documents found"}, status=404)

    data = []
    for doc in documents:
        doc_data = {"email": user.email}
        for field in DOCUMENT_FIELDS:
            doc_data[field] = getattr(doc, field) if getattr(doc, field) else None
        data.append(doc_data)

    return JsonResponse(data, safe=False)

@csrf_exempt
def create_award(request):
    if request.method == "POST":
        import json

        # Handle JSON or form data
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST

        email = data.get("email")
        user = get_object_or_404(User, email=email)

        award = Award.objects.create(
            email=user,
            title=data.get("title"),
            description=data.get("description"),
        )

        # Photo upload
        photo_file = request.FILES.get("photo")
        if photo_file:
            client = get_s3_client()
            extension = photo_file.name.split('.')[-1]
            key = f'awards/{award.id}.{extension}'
            try:
                client.upload_fileobj(photo_file, BUCKET_NAME, key, ExtraArgs={"ContentType": photo_file.content_type})
                award.photo = f"{BASE_BUCKET_URL}{key}"
                award.save()
            except Exception as e:
                return JsonResponse({"error": f"File upload failed: {str(e)}"}, status=500)

        return JsonResponse({"message": "Award created", "id": award.id})
    else:
        return JsonResponse({"error": "POST method required"}, status=405)


@csrf_exempt
def update_award(request, id):
    if request.method in ["POST", "PATCH"]:
        award = get_object_or_404(Award, id=id)

        # Handle JSON or form data
        if request.content_type == "application/json":
            import json
            data = json.loads(request.body)
        else:
            data = request.POST

        # Update text fields
        for field in ["title", "description"]:
            value = data.get(field)
            if value:
                setattr(award, field, value)

        # Update photo in MinIO
        photo_file = request.FILES.get("photo")
        if photo_file:
            client = get_s3_client()
            extension = photo_file.name.split('.')[-1]
            key = f'awards/{award.id}.{extension}'

            # Delete old photo if exists
            if award.photo and award.photo.startswith(BASE_BUCKET_URL):
                old_key = award.photo.replace(BASE_BUCKET_URL, "")
                try:
                    client.delete_object(Bucket=BUCKET_NAME, Key=old_key)
                except Exception as e:
                    print(f"Failed to delete old photo: {e}")

            # Upload new photo
            client.upload_fileobj(photo_file, BUCKET_NAME, key, ExtraArgs={"ContentType": photo_file.content_type})
            award.photo = f"{BASE_BUCKET_URL}{key}"

        award.save()
        return JsonResponse({"message": "Award updated"})


def list_awards(request):
    awards = Award.objects.all()
    data = []
    for a in awards:
        data.append({
            "id": a.id,
            "email": a.email.email,
            "title": a.title,
            "description": a.description,
            "photo": a.photo if a.photo else None,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),  # Format datetime as string
        })
    return JsonResponse(data, safe=False)


def get_award(request, id):
    a = get_object_or_404(Award, id=id)
    data = {
        "id": a.id,
        "email": a.email.email,
        "title": a.title,
        "description": a.description,
        "photo": a.photo if a.photo else None,
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),  # Include created_at
    }
    return JsonResponse(data)


@csrf_exempt
def delete_award(request, id):
    if request.method == "DELETE":
        award = get_object_or_404(Award, id=id)
        client = get_s3_client()

        # Delete photo from MinIO if it exists
        if award.photo and award.photo.startswith(BASE_BUCKET_URL):
            old_key = award.photo.replace(BASE_BUCKET_URL, "")
            try:
                client.delete_object(Bucket=BUCKET_NAME, Key=old_key)
                print(f"Deleted photo from MinIO: {old_key}")
            except Exception as e:
                print(f"Failed to delete photo from MinIO: {e}")

        award.delete()
        return JsonResponse({"message": "Award and photo deleted successfully"})
    else:
        return JsonResponse({"error": "DELETE method required"}, status=405)


# Attendance HTML page
def attendance_page(request):
    return render(request, 'attendance.html')


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [AllowAny]  # allow all requests

    # Optional: filter tickets by assigned_to if needed
    def get_queryset(self):
        return Ticket.objects.all()


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_office_attendance_view(request):
    """Mark attendance from office location (within 100m radius)"""
    try:
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")

        if latitude is None or longitude is None:
            return JsonResponse({"status": "fail", "message": "Latitude and longitude required"}, status=400)

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return JsonResponse({"status": "fail", "message": "Invalid latitude or longitude"}, status=400)

        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return JsonResponse({"status": "fail", "message": "No image provided"}, status=400)

        # Save the uploaded image temporarily
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

        employees = Employee.objects.all()
        for emp in employees:
            if not emp.profile_picture:
                continue

            # Download the profile picture from MinIO URL
            try:
                response = requests.get(emp.profile_picture, timeout=10)
                if response.status_code != 200:
                    continue

                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as emp_tmp:
                    emp_tmp.write(response.content)
                    emp_tmp_path = emp_tmp.name

                emp_img = face_recognition.load_image_file(emp_tmp_path)
                emp_encodings = face_recognition.face_encodings(emp_img)
                os.remove(emp_tmp_path)

                if not emp_encodings:
                    continue

                emp_encoding = emp_encodings[0]
                match = face_recognition.compare_faces([emp_encoding], uploaded_encoding, tolerance=0.5)

                if match[0]:
                    # Location verification (100m for office)
                    is_within_radius, distance_meters = verify_location(latitude, longitude, LOCATION_RADIUS_METERS)

                    if not is_within_radius:
                        os.remove(tmp_path)
                        return JsonResponse({
                            "status": "fail",
                            "message": f"User too far from office ({distance_meters:.2f} meters). Must be within {LOCATION_RADIUS_METERS}m."
                        }, status=400)

                    # Mark attendance
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
                            "location_type": "office"
                        }
                    )

                    if created:
                        msg = f"Office check-in marked for {emp.fullname}"
                    else:
                        if obj.check_out:
                            msg = f"Attendance already marked for today ({emp.fullname})"
                        else:
                            obj.check_out = now_time
                            obj.latitude = latitude
                            obj.longitude = longitude
                            obj.location_type = "office"
                            obj.save()
                            msg = f"Office check-out marked for {emp.fullname}"

                    os.remove(tmp_path)
                    return JsonResponse({"status": "success", "message": msg})

            except Exception as err:
                print(f"Error processing {emp.email}: {err}")
                continue

        os.remove(tmp_path)
        return JsonResponse({"status": "fail", "message": "No match found"}, status=404)

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_work_attendance_view(request):
    """Mark attendance for work from home (no location restriction)"""
    try:
        # Get optional latitude and longitude (not required for WFH)
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")

        # Convert to float if provided
        if latitude and longitude:
            try:
                latitude = float(latitude)
                longitude = float(longitude)
            except ValueError:
                latitude = None
                longitude = None

        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return JsonResponse({"status": "fail", "message": "No image provided"}, status=400)

        # Save the uploaded image temporarily
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

        employees = Employee.objects.all()
        for emp in employees:
            if not emp.profile_picture:
                continue

            # Download the profile picture from MinIO URL
            try:
                response = requests.get(emp.profile_picture, timeout=10)
                if response.status_code != 200:
                    continue

                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as emp_tmp:
                    emp_tmp.write(response.content)
                    emp_tmp_path = emp_tmp.name

                emp_img = face_recognition.load_image_file(emp_tmp_path)
                emp_encodings = face_recognition.face_encodings(emp_img)
                os.remove(emp_tmp_path)

                if not emp_encodings:
                    continue

                emp_encoding = emp_encodings[0]
                match = face_recognition.compare_faces([emp_encoding], uploaded_encoding, tolerance=0.5)

                if match[0]:
                    # Mark attendance (no location verification for WFH)
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
                            "location_type": "work"
                        }
                    )

                    if created:
                        msg = f"Work from outside check-in marked for {emp.fullname}"
                    else:
                        if obj.check_out:
                            msg = f"Attendance already marked for today ({emp.fullname})"
                        else:
                            obj.check_out = now_time
                            obj.latitude = latitude
                            obj.longitude = longitude
                            obj.location_type = "work"
                            obj.save()
                            msg = f"Work from outside check-out marked for {emp.fullname}"

                    os.remove(tmp_path)
                    return JsonResponse({"status": "success", "message": msg})

            except Exception as err:
                print(f"Error processing {emp.email}: {err}")
                continue

        os.remove(tmp_path)
        return JsonResponse({"status": "fail", "message": "No match found"}, status=404)

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_absent_employees():
    """
    Mark employees as absent if they haven't checked in by 10:45 AM IST.
    This should be run as a scheduled task daily at 10:45 AM IST.
    Skips Sundays and holidays from Holiday table.
    """
    try:
        now_ist = timezone.localtime(timezone.now(), IST)
        today = now_ist.date()
        current_time = now_ist.time()
        weekday_name = today.strftime('%A')
        
        # Check if today is Sunday
        if today.weekday() == 6:  # Sunday = 6
            return JsonResponse({
                "status": "info",
                "message": f"Today is Sunday ({weekday_name}) - No absent marking needed!",
                "date": str(today),
                "weekday": weekday_name
            }, status=200)
        
        # Check if today is a holiday
        from accounts.models import Holiday
        is_holiday = Holiday.objects.filter(date=today).exists()
        if is_holiday:
            holiday = Holiday.objects.get(date=today)
            return JsonResponse({
                "status": "info",
                "message": f"Today is a holiday: {holiday.name} - No absent marking needed!",
                "date": str(today),
                "holiday_name": holiday.name,
                "weekday": weekday_name
            }, status=200)
        
        # Check if current time is past 10:45 AM (10:45)
        deadline = time(10, 45)  # 10:45 AM
        
        if current_time < deadline:
            return JsonResponse({
                "status": "info",
                "message": "Not yet 10:45 AM IST. Absent marking skipped."
            }, status=200)
        
        # Get all active employees
        all_employees = Employee.objects.all()
        marked_absent_count = 0
        absent_employees = []
        
        for emp in all_employees:
            # Check if employee has checked in today
            attendance_exists = Attendance.objects.filter(
                email=emp.email,
                date=today,
                check_in__isnull=False
            ).exists()
            
            if not attendance_exists:
                # Check if already marked absent
                already_absent = AbsentEmployeeDetails.objects.filter(
                    email=emp.email,
                    date=today
                ).exists()
                
                if not already_absent:
                    # Mark as absent
                    AbsentEmployeeDetails.objects.create(
                        email=emp.email,
                        date=today
                    )
                    marked_absent_count += 1
                    absent_employees.append({
                        "email": emp.email.email,
                        "fullname": emp.fullname,
                        "department": emp.department
                    })
        
        return JsonResponse({
            "status": "success",
            "message": f"Marked {marked_absent_count} employees as absent for {today}",
            "date": str(today),
            "weekday": weekday_name,
            "absent_employees": absent_employees,
            "total_checked": all_employees.count()
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


token_generator = PasswordResetTokenGenerator()

# Helper function to send email asynchronously
def send_email_async(subject, plain_message, html_message, recipient_email):
    send_mail(
        subject=subject,
        message=plain_message,
        html_message=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient_email],
        fail_silently=False,
    )

class RequestPasswordResetView(APIView):
    permission_classes = []  # No auth required

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'No account found with this email'}, status=status.HTTP_404_NOT_FOUND)

        # Generate UID and token
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{uidb64}/{token}/"

        # Render HTML template (your existing template)
        html_message = render_to_string('emails/password_reset.html', {
            'reset_link': reset_link,
            'current_year': datetime.now().year
        })

        # Plain text fallback
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

        # Send email asynchronously using threading
        Thread(
            target=send_email_async,
            args=('Password Reset Request', plain_message, html_message, email)
        ).start()

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


@api_view(['POST'])
def appointment_letter(request):
    email = request.data.get('email')
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    # -------------------- Fetch Employee -------------------- #
    employee = Employee.objects.filter(email__email=email).first()
    if not employee:
        return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    # -------------------- Get corresponding User (directly from OneToOneField) -------------------- #
    user = employee.email  # Already a User instance

    # -------------------- Dates & File Setup -------------------- #
    today = timezone.localtime().date()
    acceptance_deadline = today + timedelta(days=5)
    folder_name = email.split('@')[0].lower()

    # -------------------- Render Context -------------------- #
    context = {
        'employee_name': employee.fullname,
        'designation': employee.designation or 'Employee',
        'joining_date': (
            employee.date_joined.strftime('%d-%m-%Y') if employee.date_joined else today.strftime('%d-%m-%Y')
        ),
        'department': employee.department or 'N/A',
        'reporting_manager': (
            employee.reports_to.email if employee.reports_to else 'N/A'
        ),
        'logo_url': 'https://www.globaltechsoftwaresolutions.com/_next/image?url=%2Flogo%2FGlobal.jpg&w=64&q=75',
        'company_name': 'Global Tech Software Solutions',
        'salary': 'Confidential',
        'today_date': today.strftime('%d-%m-%Y'),
        'acceptance_deadline': acceptance_deadline.strftime('%d-%m-%Y'),
    }

    # -------------------- Render HTML to PDF -------------------- #
    html = render_to_string('letters/appointment_letter.html', context)

    pdf_minio = BytesIO()
    pdf_email = BytesIO()

    pisa_status_minio = pisa.CreatePDF(html, dest=pdf_minio, encoding='UTF-8')
    if pisa_status_minio.err:
        return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    if pisa_status_email.err:
        return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "appointment_letter.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        s3 = boto3.client(
            's3',
            endpoint_url='https://minio.globaltechsoftwaresolutions.cloud:9000',
            aws_access_key_id='admin',
            aws_secret_access_key='admin12345'
        )

        bucket_name = 'hrms-media'
        s3.upload_fileobj(
            pdf_minio,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        file_url = f"https://minio.globaltechsoftwaresolutions.cloud:9000/{bucket_name}/{object_name}"

        # Save the MinIO file URL to Document model
        document, _ = Document.objects.get_or_create(email=user)
        document.appointment_letter = file_url
        document.save()

    except Exception as e:
        return Response({"error": f"MinIO upload or DB save failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Send Email -------------------- #
    try:
        pdf_email.seek(0)
        pdf_content = pdf_email.read()

        mail = EmailMessage(
            subject="Appointment Letter - Global Tech Software Solutions",
            body=f"Dear {employee.fullname},\n\nPlease find attached your appointment letter.\n\nBest Regards,\nGlobal Tech HR",
            to=[email]
        )
        mail.attach(filename, pdf_content, 'application/pdf')
        mail.send(fail_silently=False)

    except Exception as e:
        return Response({"error": f"Failed to send email: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Success -------------------- #
    return Response({
        "message": "Appointment letter generated, uploaded to MinIO, saved in DB, and emailed successfully.",
        "employee": employee.fullname,
        "file_url": file_url
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
def offer_letter(request):
    email = request.data.get('email')
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    # -------------------- Fetch Employee -------------------- #
    employee = Employee.objects.filter(email__email=email).first()
    if not employee:
        return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    # -------------------- Fetch corresponding User -------------------- #
    user = employee.email  # Already a User instance due to OneToOneField

    # -------------------- Prepare Context for Offer Letter -------------------- #
    today = timezone.now().date()
    acceptance_deadline = today + timedelta(days=5)
    folder_name = email.split('@')[0].lower()

    context = {
        'candidate_name': employee.fullname,
        'designation': employee.designation or 'Employee',
        'location': employee.work_location or 'Bangalore',
        'joining_date': employee.date_joined or today,
        'today_date': today,
        'probation_months': 6,
        'acceptance_deadline': acceptance_deadline,
        'logo_url': 'https://www.globaltechsoftwaresolutions.com/_next/image?url=%2Flogo%2FGlobal.jpg&w=64&q=75',
        'company_name': 'Global Tech Software Solutions',
    }

    # -------------------- Render HTML to PDF -------------------- #
    html = render_to_string('letters/offer_letter.html', context)

    # Create in-memory PDFs
    pdf_minio = BytesIO()
    pdf_email = BytesIO()

    pisa_status_minio = pisa.CreatePDF(html, dest=pdf_minio, encoding='UTF-8')
    if pisa_status_minio.err:
        return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    if pisa_status_email.err:
        return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "offer_letter.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        s3 = boto3.client(
            's3',
            endpoint_url='https://minio.globaltechsoftwaresolutions.cloud:9000',
            aws_access_key_id='admin',
            aws_secret_access_key='admin12345'
        )

        bucket_name = 'hrms-media'
        s3.upload_fileobj(
            pdf_minio,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        file_url = f"https://minio.globaltechsoftwaresolutions.cloud:9000/{bucket_name}/{object_name}"

        # Save the MinIO file URL to Document model
        document, _ = Document.objects.get_or_create(email=user)
        document.offer_letter = file_url
        document.save()

    except Exception as e:
        return Response({"error": f"MinIO upload or DB save failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Send Offer Letter via Email -------------------- #
    try:
        pdf_email.seek(0)
        pdf_content = pdf_email.read()

        mail = EmailMessage(
            subject="Offer Letter - Global Tech Software Solutions",
            body=f"Dear {employee.fullname},\n\nPlease find attached your offer letter.\n\nBest Regards,\nGlobal Tech HR",
            to=[email]
        )
        mail.attach(filename, pdf_content, 'application/pdf')
        mail.send(fail_silently=False)

    except Exception as e:
        return Response({"error": f"Failed to send email: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Success Response -------------------- #
    return Response({
        "message": "Offer letter generated, uploaded to MinIO, saved in DB, and emailed successfully.",
        "employee": employee.fullname,
        "file_url": file_url
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
def releaving_letter(request):
    email = request.data.get('email')
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    # -------------------- Fetch Employee -------------------- #
    employee = Employee.objects.filter(email__email=email).first()
    if not employee:
        return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    # -------------------- Fetch corresponding User -------------------- #
    user = employee.email  # Already a User instance

    today = timezone.now().date()
    last_working_day = getattr(employee, 'last_working_date', today)
    folder_name = email.split('@')[0].lower()

    # -------------------- Render PDF -------------------- #
    context = {
        'employee_name': employee.fullname,
        'employee_id': getattr(employee, 'emp_id', '') or getattr(employee, 'id', ''),
        'designation': employee.designation or 'Employee',
        'department': employee.department or '',
        'date_of_joining': employee.date_joined or today,
        'last_working_day': last_working_day,
        'resignation_effective_date': last_working_day,
        'issue_date': today,
        'company_name': 'Global Tech Software Solutions',
        'logo_url': 'https://www.globaltechsoftwaresolutions.com/_next/image?url=%2Flogo%2FGlobal.jpg&w=64&q=75',
    }

    html = render_to_string('letters/releaving_letter.html', context)

    # -------------------- Generate PDFs -------------------- #
    pdf_minio = BytesIO()
    pdf_email = BytesIO()

    if pisa.CreatePDF(html, dest=pdf_minio, encoding='UTF-8').err:
        return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    if pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8').err:
        return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "releaving_letter.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        s3 = boto3.client(
            's3',
            endpoint_url='https://minio.globaltechsoftwaresolutions.cloud:9000',
            aws_access_key_id='admin',
            aws_secret_access_key='admin12345'
        )
        bucket_name = 'hrms-media'
        s3.upload_fileobj(pdf_minio, bucket_name, object_name, ExtraArgs={'ContentType': 'application/pdf'})

        file_url = f"https://minio.globaltechsoftwaresolutions.cloud:9000/{bucket_name}/{object_name}"

        # Save URL to Document
        document, _ = Document.objects.get_or_create(email=user)
        document.releaving_letter = file_url
        document.save()

    except Exception as e:
        return Response({"error": f"MinIO upload or DB save failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Send Email -------------------- #
    try:
        pdf_email.seek(0)
        pdf_content = pdf_email.read()

        mail = EmailMessage(
            subject="Relieving Letter - Global Tech Software Solutions",
            body=f"Dear {employee.fullname},\n\nPlease find attached your relieving letter.\n\nBest Regards,\nGlobal Tech HR",
            to=[email]
        )
        mail.attach(filename, pdf_content, 'application/pdf')
        mail.send(fail_silently=False)

    except Exception as e:
        return Response({"error": f"Failed to send email: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        "message": "Relieving letter generated, uploaded to MinIO, saved in DB, and emailed successfully.",
        "employee": employee.fullname,
        "file_url": file_url
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
def bonafide_certificate(request):
    email = request.data.get('email')
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    # -------------------- Fetch Employee -------------------- #
    # Since Employee.email is a OneToOneField to User.email, use double lookup
    employee = Employee.objects.filter(email__email=email).first()
    if not employee:
        return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

    # -------------------- Get corresponding User instance -------------------- #
    user = employee.email  # This is already a User object due to OneToOneField

    # -------------------- Prepare Context -------------------- #
    today = timezone.localtime().date()
    last_working_day = today
    folder_name = email.split('@')[0].lower()

    context = {
        'candidate_name': employee.fullname,
        'email': user.email,
        'designation': employee.designation or "Employee",
        'department': employee.department or "N/A",
        'date_of_joining': employee.date_joined.strftime("%d-%m-%Y") if employee.date_joined else "N/A",
        'last_working_day': last_working_day.strftime("%d-%m-%Y"),
        'resignation_effective_date': last_working_day.strftime("%d-%m-%Y"),
        'issue_date': today.strftime("%d-%m-%Y"),
        'company_name': 'Global Tech Software Solutions',
        'logo_url': 'https://www.globaltechsoftwaresolutions.com/_next/image?url=%2Flogo%2FGlobal.jpg&w=64&q=75'
    }

    # -------------------- Render HTML to PDF -------------------- #
    html = render_to_string('letters/bonafide_certificate.html', context)

    # Create in-memory PDFs
    pdf_minio = BytesIO()
    pdf_email = BytesIO()

    pisa_status_minio = pisa.CreatePDF(html, dest=pdf_minio, encoding='UTF-8')
    if pisa_status_minio.err:
        return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    if pisa_status_email.err:
        return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "bonafide_crt.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        s3 = boto3.client(
            's3',
            endpoint_url='https://minio.globaltechsoftwaresolutions.cloud:9000',
            aws_access_key_id='admin',
            aws_secret_access_key='admin12345'
        )

        bucket_name = 'hrms-media'
        s3.upload_fileobj(
            pdf_minio,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        file_url = f"https://minio.globaltechsoftwaresolutions.cloud:9000/{bucket_name}/{object_name}"

        # Save URL to DB
        document, _ = Document.objects.get_or_create(email=user)
        document.bonafide_crt = file_url
        document.save()

    except Exception as e:
        return Response({"error": f"MinIO upload or DB save failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Send Email -------------------- #
    try:
        pdf_email.seek(0)
        pdf_content = pdf_email.read()

        mail = EmailMessage(
            subject="Bonafide Certificate - Global Tech Software Solutions",
            body=f"Dear {employee.fullname},\n\nPlease find attached your Bonafide Certificate.\n\nBest Regards,\nGlobal Tech HR",
            to=[user.email]
        )
        mail.attach(filename, pdf_content, 'application/pdf')
        mail.send(fail_silently=False)

    except Exception as e:
        return Response({"error": f"Failed to send email: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------- Success Response -------------------- #
    return Response({
        "message": "Bonafide certificate generated, uploaded to MinIO, saved in DB, and emailed successfully.",
        "employee": employee.fullname,
        "file_url": file_url
    }, status=status.HTTP_200_OK)


class HolidayViewSet(viewsets.ModelViewSet):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        many = isinstance(data, list)
        created_objects = []

        if many:
            for item in data:
                try:
                    holiday, created = Holiday.objects.get_or_create(
                        date=item.get("date"),
                        country=item.get("country"),
                        defaults={
                            "name": item.get("name"),
                            "type": item.get("type"),
                            "year": item.get("year"),
                            "month": item.get("month"),
                            "weekday": item.get("weekday")
                        }
                    )
                    if created:
                        created_objects.append(HolidaySerializer(holiday).data)
                except IntegrityError:
                    continue  # skip duplicates
            return Response(created_objects, status=status.HTTP_201_CREATED)
        else:
            # single entry
            try:
                holiday, created = Holiday.objects.get_or_create(
                    date=data.get("date"),
                    country=data.get("country"),
                    defaults={
                        "name": data.get("name"),
                        "type": data.get("type"),
                        "year": data.get("year"),
                        "month": data.get("month"),
                        "weekday": data.get("weekday")
                    }
                )
                serializer = HolidaySerializer(holiday)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except IntegrityError:
                return Response({"detail": "Holiday already exists"}, status=status.HTTP_400_BAD_REQUEST)
            

@api_view(['GET'])
def list_absent_employees(request):
    absent_employees = AbsentEmployeeDetails.objects.all()
    serializer = AbsentEmployeeDetailsSerializer(absent_employees, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def get_absent_employee(request, email):
    """Get absent employee details for a specific email"""
    user = get_object_or_404(User, email=email)
    absent_records = AbsentEmployeeDetails.objects.filter(email=user)
    serializer = AbsentEmployeeDetailsSerializer(absent_records, many=True)
    return Response(serializer.data)


class CareerViewSet(viewsets.ModelViewSet):
    queryset = JobPosting.objects.all()
    serializer_class = CareerSerializer
    lookup_field = 'id'  # JobPosting uses 'id' as primary key, not 'email'
    

def upload_resume(instance, file_obj):
    client = get_s3_client()
    ext = file_obj.name.split('.')[-1]
    key = f'careers_resume/{instance.email}.{ext}'

    # Delete old resume if exists
    if instance.resume and instance.resume != f"{BASE_BUCKET_URL}{key}":
        old_key = instance.resume.replace(BASE_BUCKET_URL, "")
        try:
            client.delete_object(Bucket=BUCKET_NAME, Key=old_key)
        except Exception as e:
            print(f"Failed to delete old resume: {e}")

    # ✅ Allow both PDF and images
    content_type = file_obj.content_type or "application/octet-stream"
    client.upload_fileobj(file_obj, BUCKET_NAME, key, ExtraArgs={"ContentType": content_type})
    instance.resume = f"{BASE_BUCKET_URL}{key}"
    instance.save()


# ------------------- ViewSet -------------------
@method_decorator(csrf_exempt, name='dispatch')  # ✅ CSRF disabled for this viewset
class AppliedJobViewSet(viewsets.ModelViewSet):
    queryset = AppliedJobs.objects.all()
    serializer_class = AppliedJobSerializer
    lookup_field = 'email'
    permission_classes = [AllowAny]  # Allow all (adjust if you add auth later)

    def create(self, request, *args, **kwargs):
        """Create a new job application"""
        data = request.data.copy()
        resume_file = request.FILES.get('resume')

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        if resume_file:
            upload_resume(instance, resume_file)

        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        """Update any field (like hired status, specialization, etc.)"""
        instance = self.get_object()
        old_hired = instance.hired

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # ✅ Send email if hired changed from False → True
        if not old_hired and instance.hired:
            self.send_hired_email(instance)

        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['patch'], url_path='set-hired')
    def set_hired(self, request, email=None):
        """✅ API to set hired=True for a candidate"""
        instance = get_object_or_404(AppliedJobs, email=email)
        if not instance.hired:
            instance.hired = True
            instance.save()
            self.send_hired_email(instance)
            return Response({"message": f"{instance.fullname} is now hired."}, status=status.HTTP_200_OK)
        return Response({"message": f"{instance.fullname} was already marked as hired."}, status=status.HTTP_200_OK)

    def send_hired_email(self, instance):
        """📩 Send email to candidate when hired"""
        subject = "🎉 Congratulations! You’re Hired!"
        body = f"""
Dear {instance.fullname},

We are delighted to inform you that you have been successfully selected for the Global Tech Software Solutions.
Our HR department will contact you shortly with details regarding your onboarding process, joining date, and documentation requirements.

Welcome to Global Tech Software Solutions — we look forward to working with you!

Warm regards,  
HR Department  
Global Tech Software Solutions
"""
        try:
            email_msg = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [instance.email])
            email_msg.send(fail_silently=False)
            print(f"✅ Hired email sent to {instance.email}")
        except Exception as e:
            print(f"⚠️ Failed to send hired email: {e}")

    def destroy(self, request, email=None):
        """Delete application and remove resume from S3 if exists"""
        instance = get_object_or_404(AppliedJobs, email=email)

        if instance.resume:
            client = get_s3_client()
            key = instance.resume.replace(BASE_BUCKET_URL, "")
            try:
                client.delete_object(Bucket=BUCKET_NAME, Key=key)
            except Exception as e:
                print(f"Failed to delete resume: {e}")

        instance.delete()
        return Response({"message": f"Application for {email} deleted."}, status=status.HTTP_200_OK)
 
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import Employee, EmployeeDetails, ReleavedEmployee

User = get_user_model()  # Correct way to get custom user model

@csrf_exempt
@api_view(['POST'])
def transfer_to_releaved(request):
    """
    Transfer an employee to ReleavedEmployee table.
    Expects JSON: { "email": "employee_email@example.com", "reason_for_resignation": "..." }
    """
    email = request.data.get('email')
    reason_for_resignation = request.data.get('reason_for_resignation', '')
    
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
        employee = Employee.objects.get(email=user)
        details = EmployeeDetails.objects.get(email=user)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except Employee.DoesNotExist:
        return Response({"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)
    except EmployeeDetails.DoesNotExist:
        return Response({"error": "EmployeeDetails not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check if already exists in ReleavedEmployee (by email string)
    existing_releaved = ReleavedEmployee.objects.filter(email=email).first()
    if existing_releaved:
        # If previous resignation was rejected (approved='no'), delete it and allow reapplication
        if existing_releaved.approved == 'no':
            existing_releaved.delete()
        # If still pending (approved=None) or approved='yes', prevent duplicate
        elif existing_releaved.approved in [None, 'yes']:
            status_msg = "pending approval" if existing_releaved.approved is None else "already approved"
            return Response({"message": f"{email} resignation is {status_msg}."}, status=status.HTTP_400_BAD_REQUEST)

    # Create ReleavedEmployee with email as string
    data = {
        'email': email,  # Store email as string, not User FK
        'fullname': employee.fullname,
        'phone': employee.phone,
        'role': user.role,
        'department': employee.department,
        'designation': employee.designation,
        'date_of_birth': employee.date_of_birth,
        'date_joined': employee.date_joined,
        'profile_picture': employee.profile_picture,
        'skills': employee.skills,
        'gender': employee.gender,
        'marital_status': employee.marital_status,
        'nationality': employee.nationality,
        'residential_address': employee.residential_address,
        'permanent_address': employee.permanent_address,
        'emergency_contact_name': employee.emergency_contact_name,
        'emergency_contact_relationship': employee.emergency_contact_relationship,
        'emergency_contact_no': employee.emergency_contact_no,
        'emp_id': employee.emp_id,
        'employment_type': employee.employment_type,
        'work_location': employee.work_location,
        'team': employee.team,
        'degree': employee.degree,
        'degree_passout_year': employee.degree_passout_year,
        'institution': employee.institution,
        'grade': employee.grade,
        'languages': employee.languages,
        'blood_group': employee.blood_group,
        # EmployeeDetails fields
        'account_number': details.account_number,
        'father_name': details.father_name,
        'father_contact': details.father_contact,
        'mother_name': details.mother_name,
        'mother_contact': details.mother_contact,
        'wife_name': details.wife_name,
        'home_address': details.home_address,
        'total_siblings': details.total_siblings,
        'brothers': details.brothers,
        'sisters': details.sisters,
        'total_children': details.total_children,
        'bank_name': details.bank_name,
        'branch': details.branch,
        'pf_no': details.pf_no,
        'pf_uan': details.pf_uan,
        'ifsc': details.ifsc,
        'reason_for_resignation': reason_for_resignation,
        'approved': None,
    }

    releaved = ReleavedEmployee.objects.create(**data)

    return Response({"message": f"{email} transferred to ReleavedEmployee."}, status=status.HTTP_201_CREATED)



@csrf_exempt
@api_view(['PATCH'])
def approve_releaved(request, email):
    """
    Approve a releaved employee:
    - Update ReleavedEmployee row (approved, description)
    - Delete related Employee, EmployeeDetails, and User if approved='yes'
    - Keep ReleavedEmployee row intact (email is stored as string, not FK)
    - Send email notification about approval/rejection
    """
    approved = request.data.get('approved')
    description = request.data.get('description', '')

    if approved not in ['yes', 'no']:
        return Response({"error": "approved must be 'yes' or 'no'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Use email string lookup instead of email__email
        releaved = ReleavedEmployee.objects.get(email=email)
    except ReleavedEmployee.DoesNotExist:
        return Response({"error": "ReleavedEmployee not found."}, status=status.HTTP_404_NOT_FOUND)

    # Update the ReleavedEmployee row
    releaved.approved = approved
    releaved.description = description
    releaved.offboarded_at = timezone.now()
    releaved.save()

    # Prepare email content
    employee_name = releaved.fullname or email
    designation = releaved.designation or "Employee"
    
    # Convert to IST timezone for display
    offboarding_date_ist = timezone.localtime(releaved.offboarded_at, IST) if releaved.offboarded_at else None
    offboarding_date = offboarding_date_ist.strftime('%B %d, %Y at %I:%M %p') if offboarding_date_ist else 'N/A'
    offboarding_date_plain = offboarding_date_ist.strftime('%Y-%m-%d %H:%M:%S IST') if offboarding_date_ist else 'N/A'

    if approved == 'yes':
        # Send approval email using template
        subject = "Resignation Approved - Offboarding Confirmation"
        
        html_message = render_to_string('emails/resignation_approved.html', {
            'employee_name': employee_name,
            'designation': designation,
            'email': email,
            'offboarding_date': offboarding_date,
            'reason_for_resignation': releaved.reason_for_resignation,
            'description': description,
            'current_year': datetime.now().year
        })
        
        plain_message = f"""Dear {employee_name},

Your resignation has been approved.

Employee Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
- Offboarding Date: {offboarding_date_plain}
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

{description if description else 'Thank you for your contributions to the organization. We wish you all the best in your future endeavors.'}

Best regards,
HR Department
Global Tech Software Solutions
"""
        
        try:
            # Send email asynchronously
            Thread(
                target=send_email_async,
                args=(subject, plain_message, html_message, email)
            ).start()
        except Exception as e:
            print(f"Failed to send approval email to {email}: {str(e)}")
        
        # Send notification to all CEOs and Managers about successful offboarding
        try:
            from accounts.models import CEO, Manager
            
            # Get all CEOs and Managers
            ceos = CEO.objects.all()
            managers = Manager.objects.all()
            
            # Prepare notification email for leadership
            leadership_subject = f"Employee Offboarding Notification - {employee_name}"
            
            leadership_plain_message = f"""Dear Leadership,

This is to inform you that an employee has been successfully offboarded from the organization.

Employee Offboarding Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
- Department: {releaved.department or 'N/A'}
- Offboarding Date: {offboarding_date_plain}
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

Status: Approved and Offboarded

{description if description else 'The employee has completed the offboarding process.'}

This is an automated notification from the HR system.

Best regards,
HR Department
Global Tech Software Solutions
"""
            
            # Use template for HTML email
            leadership_html_message = render_to_string('emails/employee_offboarded_leadership.html', {
                'employee_name': employee_name,
                'designation': designation,
                'email': email,
                'department': releaved.department or 'N/A',
                'offboarding_date': offboarding_date,
                'reason_for_resignation': releaved.reason_for_resignation,
                'description': description,
                'current_year': datetime.now().year
            })
            
            # Send to all CEOs
            for ceo in ceos:
                try:
                    Thread(
                        target=send_email_async,
                        args=(leadership_subject, leadership_plain_message, leadership_html_message, ceo.email.email)
                    ).start()
                except Exception as e:
                    print(f"Failed to send offboarding notification to CEO {ceo.email.email}: {str(e)}")
            
            # Send to all Managers
            for manager in managers:
                try:
                    Thread(
                        target=send_email_async,
                        args=(leadership_subject, leadership_plain_message, leadership_html_message, manager.email.email)
                    ).start()
                except Exception as e:
                    print(f"Failed to send offboarding notification to Manager {manager.email.email}: {str(e)}")
            
            print(f"Offboarding notifications sent to {ceos.count()} CEOs and {managers.count()} Managers")
            
        except Exception as e:
            print(f"Failed to send offboarding notifications to leadership: {str(e)}")
        
        try:
            # Find and delete User by email string
            user = User.objects.filter(email=email).first()
            if user:
                # Delete related records (signals will handle backup)
                Employee.objects.filter(email=user).delete()
                EmployeeDetails.objects.filter(email=user).delete()
                user.delete()  # Delete the User
                
                # ReleavedEmployee is unaffected since email is now a plain string field
        except Exception as e:
            return Response({"error": f"Failed to delete related records: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "message": f"{email} approval set to {approved}. Employee, EmployeeDetails, and User deleted. ReleavedEmployee preserved. Approval email sent to employee and offboarding notifications sent to all CEOs and Managers."
        }, status=status.HTTP_200_OK)
    
    else:  # approved == 'no'
        # Send rejection email using template
        subject = "Resignation Request - Update"
        
        html_message = render_to_string('emails/resignation_rejected.html', {
            'employee_name': employee_name,
            'designation': designation,
            'email': email,
            'reason_for_resignation': releaved.reason_for_resignation,
            'description': description,
            'current_year': datetime.now().year
        })
        
        plain_message = f"""Dear {employee_name},

Regarding your resignation request:

Employee Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
- Status: Rejected / On Hold
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

{description if description else 'Please contact HR department for further discussion regarding your resignation request.'}

Best regards,
HR Department
Global Tech Software Solutions
"""
        
        try:
            # Send email asynchronously
            Thread(
                target=send_email_async,
                args=(subject, plain_message, html_message, email)
            ).start()
        except Exception as e:
            print(f"Failed to send rejection email to {email}: {str(e)}")
        
        # Rejection - keep the record with approved='no' status
        # Employee can reapply (transfer_to_releaved will handle deletion of rejected record)
        return Response({
            "message": f"{email} resignation rejected. Record marked as rejected. Rejection email sent."
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
def list_releaved_employees(request):
    """
    Get all relieved employees with optional filtering
    Query params:
    - approved: Filter by approval status ('yes', 'no', or 'pending')
    - department: Filter by department
    - designation: Filter by designation
    """
    releaved_employees = ReleavedEmployee.objects.all().order_by('-offboarded_at')
    
    # Apply filters
    approved_filter = request.GET.get('approved')
    if approved_filter:
        if approved_filter == 'pending':
            releaved_employees = releaved_employees.filter(approved__isnull=True)
        else:
            releaved_employees = releaved_employees.filter(approved=approved_filter)
    
    department_filter = request.GET.get('department')
    if department_filter:
        releaved_employees = releaved_employees.filter(department__icontains=department_filter)
    
    designation_filter = request.GET.get('designation')
    if designation_filter:
        releaved_employees = releaved_employees.filter(designation__icontains=designation_filter)
    
    serializer = ReleavedEmployeeSerializer(releaved_employees, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_releaved_employee(request, email):
    """
    Get single relieved employee by email
    Returns full details including resignation reason and approval status
    """
    try:
        releaved = ReleavedEmployee.objects.get(email=email)
        serializer = ReleavedEmployeeSerializer(releaved)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except ReleavedEmployee.DoesNotExist:
        return Response({
            "error": "Relieved employee not found.",
            "email": email
        }, status=status.HTTP_404_NOT_FOUND)
