import os, json, pytz, face_recognition, tempfile, requests, boto3

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
    RaiseRequestAttendance, JobPosting, PettyCash
)

# Serializers
from .serializers import (
    UserSerializer, CEOSerializer, HRSerializer, ManagerSerializer, DepartmentSerializer,
    EmployeeSerializer, SuperUserCreateSerializer, UserRegistrationSerializer, ProjectSerializer,
    AdminSerializer, ReportSerializer, RegisterSerializer, DocumentSerializer, AwardSerializer, TicketSerializer, EmployeeDetailsSerializer, HolidaySerializer, AbsentEmployeeDetailsSerializer, CareerSerializer, AppliedJobSerializer, ReleavedEmployeeSerializer, PettyCashSerializer
)

# Ensure User model points to custom one
User = get_user_model()

# Constants
OFFICE_LAT = 13.068906816007116
OFFICE_LON = 77.55541294505542
LOCATION_RADIUS_METERS = 1000  # 100m allowed radius
from .constants import IST, CHECK_IN_START, CHECK_IN_DEADLINE


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
            # Check if user has the role attribute before accessing it
            if hasattr(user, 'role') and getattr(user, 'role', None) != role:
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
        # Fixed: Use setattr to avoid type checking issues
        if hasattr(user, 'is_staff'):
            setattr(user, 'is_staff', True)  # Mark user as staff (approved)
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
        bucket_name = settings.MINIO_STORAGE["BUCKET_NAME"]
        base_url = settings.BASE_BUCKET_URL

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


# ------------------- MinIO Client -------------------
def get_s3_client():
    minio_conf = settings.MINIO_STORAGE
    protocol = "https" if minio_conf.get("USE_SSL", False) else "http"
    client = boto3.client(
        "s3",
        endpoint_url=f"{protocol}://{minio_conf['ENDPOINT']}",
        aws_access_key_id=minio_conf["ACCESS_KEY"],
        aws_secret_access_key=minio_conf["SECRET_KEY"],
        verify=True
    )
    return client

BASE_BUCKET_URL = settings.BASE_BUCKET_URL
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
                        if hasattr(related_model, 'email'):  # Check if related model has email field
                            related_instance = related_model.objects.get(email=value)
                        else:
                            related_instance = related_model.objects.get(pk=value)
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

            # 3️⃣ Delete related EmployeeDetails
            try:
                user_obj = User.objects.filter(email=email_str).first()
                if user_obj:
                    EmployeeDetails.objects.filter(email=user_obj).delete()
            except Exception as e:
                print(f"[WARN] Error deleting EmployeeDetails: {e}")

            # 4️⃣ Delete profile picture from MinIO
            if hasattr(employee, "profile_picture") and employee.profile_picture:
                client = get_s3_client()
                key = employee.profile_picture.replace(BASE_BUCKET_URL, "")
                try:
                    client.delete_object(Bucket=BUCKET_NAME, Key=key)
                except Exception as e:
                    print(f"[WARN] Failed to delete profile picture from MinIO: {e}")

            # 5️⃣ Delete main Employee and related User safely
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
    queryset = ReleavedEmployee.objects.all().order_by('-applied_at')
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
            paid_status=data.get("paid_status", None),
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
                "status": leave.status,
                "paid_status": leave.paid_status
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
        new_paid_status = data.get("paid_status")

        if new_status and new_status not in ["Approved", "Rejected"]:
            return JsonResponse({"error": "Invalid status. Must be Approved or Rejected."}, status=400)

        if new_status:
            leave.status = new_status
        if new_paid_status:
            leave.paid_status = new_paid_status
        leave.save()

        return JsonResponse({
            "message": f"Leave request updated",
            "leave": {
                "email": leave.email.email,
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "leave_type": leave.leave_type,
                "reason": leave.reason,
                "status": leave.status,
                "paid_status": leave.paid_status
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
            "status": leave.status,
            "paid_status": leave.paid_status
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
            "paid_status": leave.paid_status,
            "applied_on": str(leave.applied_on)
        })

    return JsonResponse({"leaves": result}, status=200)


def calculate_lop_days(user, month, year):
    """
    Calculate LOP (Loss of Pay) days based on approved unpaid leaves for a given month/year
    """
    # Get all approved unpaid leaves for this employee
    unpaid_leaves = Leave.objects.filter(
        email=user,
        status="Approved",
        paid_status="Unpaid"
    )
    
    lop_days = 0
    target_month = int(month)
    target_year = int(year)
    
    import calendar
    from datetime import date
    
    # Get the first and last day of the target month
    first_day = date(target_year, target_month, 1)
    last_day = date(target_year, target_month, calendar.monthrange(target_year, target_month)[1])
    
    for leave in unpaid_leaves:
        # Check if the leave overlaps with the target month
        if leave.start_date <= last_day and leave.end_date >= first_day:
            # Calculate the overlapping period
            overlap_start = max(leave.start_date, first_day)
            overlap_end = min(leave.end_date, last_day)
            
            # Add the number of overlapping days (inclusive)
            lop_days += (overlap_end - overlap_start).days + 1
            
    return lop_days


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

        # Calculate LOP (Loss of Pay) days based on unpaid leaves
        calculated_lop = calculate_lop_days(user, month, year)
        
        # Use provided LOP value or calculated one
        lop_value = data.get("LOP", calculated_lop)

        # Create new payroll entry
        payroll = Payroll.objects.create(
            email=user,
            basic_salary=data.get("basic_salary", 0.00),
            month=month,
            year=year,
            status=data.get("status", "Pending"),
            STD=data.get("STD", 0),
            LOP=lop_value,
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
        recalculate_lop = data.get("recalculate_lop", False)

        if new_status and new_status not in ["Pending", "Paid", "Failed"]:
            return JsonResponse({"error": "Invalid status"}, status=400)

        # Update fields if provided
        if new_status:
            payroll.status = new_status
            
        if "STD" in data:
            payroll.STD = data["STD"]
            
        if "LOP" in data:
            payroll.LOP = data["LOP"]
        elif recalculate_lop:
            # Recalculate LOP based on unpaid leaves
            calculated_lop = calculate_lop_days(payroll.email, payroll.month, payroll.year)
            payroll.LOP = calculated_lop
            
        if "basic_salary" in data:
            payroll.basic_salary = data["basic_salary"]

        payroll.save()

        return JsonResponse({
            "message": f"Payroll status updated to {payroll.status}",
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
            "id": payroll.id,
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
            "id": payroll.id,
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
            "email": report.email.email if report.email else None,
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
        project_status = data.get("status", "Planning")  # Renamed to avoid conflict
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        description = data.get("description")

        # Create project instance (without members for now)
        project = Project.objects.create(
            name=name,
            description=description,
            status=project_status,
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
            # Fixed: Use primary keys to avoid type issues
            project.members.set(list(members.values_list('pk', flat=True)))

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
    

DOCUMENT_FIELDS = [
    "tenth", "twelth", "degree", "masters", "marks_card", "certificates",
    "award", "resume", "id_proof", "appointment_letter", "offer_letter",
    "releaving_letter", "resignation_letter", "achievement_crt", "bonafide_crt",
]

# Use BASE_BUCKET_URL from settings.py
BASE_BUCKET_URL = settings.BASE_BUCKET_URL

# CREATE Document
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

    # Fixed: Document model doesn't have an id field, using email as identifier
    return JsonResponse({
        "message": "Document created successfully",
        "email": document.email.email,
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
    # Fixed: Removed problematic deletion line

    folder_name = email.split("@")[0].lower()
    client = get_s3_client()
    bucket_name = settings.MINIO_STORAGE["BUCKET_NAME"]
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
    bucket_name = settings.MINIO_STORAGE["BUCKET_NAME"]
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
        # Fixed: Document model doesn't have an id field, use email as identifier
        doc_data = {"email": doc.email.email}
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
        # Fixed: Document model doesn't have an id field
        # Fixed: Access user.email properly
        doc_data = {"email": getattr(user, 'email', email)}
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
            # Fixed: Use pk instead of id for award
            key = f'awards/{award.pk}.{extension}'
            try:
                client.upload_fileobj(photo_file, BUCKET_NAME, key, ExtraArgs={"ContentType": photo_file.content_type})
                award.photo = f"{BASE_BUCKET_URL}{key}"
                award.save()
            except Exception as e:
                return JsonResponse({"error": f"File upload failed: {str(e)}"}, status=500)

        # Fixed: Use pk instead of id for award
        return JsonResponse({"message": "Award created", "pk": award.pk})
    else:
        return JsonResponse({"error": "POST method required"}, status=405)


@csrf_exempt
@require_http_methods(["POST", "PATCH"])
def update_award(request, pk):
    award = get_object_or_404(Award, pk=pk)

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
        # Fixed: Use pk instead of id for award
        key = f'awards/{award.pk}.{extension}'

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
        # Fixed: Use pk instead of id for award
        data.append({
            "pk": a.pk,
            "email": a.email.email,
            "title": a.title,
            "description": a.description,
            "photo": a.photo if a.photo else None,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),  # Format datetime as string
        })
    return JsonResponse(data, safe=False)


def get_award(request, pk):
    a = get_object_or_404(Award, pk=pk)
    # Fixed: Use pk instead of id for award
    data = {
        "pk": a.pk,
        "email": a.email.email,
        "title": a.title,
        "description": a.description,
        "photo": a.photo if a.photo else None,
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),  # Include created_at
    }
    return JsonResponse(data)


def delete_award(request, pk):
    if request.method == "DELETE":
        award = get_object_or_404(Award, pk=pk)
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


IST = timezone.get_fixed_timezone(330)  # IST is UTC+5:30
CHECK_IN_DEADLINE = time(10, 45)  # 10:45 AM
LOCATION_RADIUS_METERS = 1000  # 100 meters

def get_all_users_with_photos():
    """Return all users from Employee, HR, CEO, Manager, and Admin models that have profile pictures."""
    from accounts.models import Employee, HR, CEO, Manager, Admin

    user_types = [Employee, HR, CEO, Manager, Admin]
    all_users = []

    for model in user_types:
        all_users += list(model.objects.exclude(profile_picture__isnull=True).exclude(profile_picture=""))
    
    return all_users


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_office_attendance_view(request):
    """Mark attendance from office location (within 1000m radius)"""
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

        # Save uploaded image temporarily
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

        # Current date/time in IST
        now_ist = timezone.localtime(timezone.now(), IST)
        today = now_ist.date()
        current_time = now_ist.time()

        # Loop through all user types
        people = get_all_users_with_photos()
        for person in people:
            if not person.profile_picture:
                continue

            try:
                response = requests.get(person.profile_picture, timeout=10)
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
                    # Verify location (office radius)
                    is_within_radius, distance_meters = verify_location(latitude, longitude, LOCATION_RADIUS_METERS)

                    if not is_within_radius:
                        os.remove(tmp_path)
                        return JsonResponse({
                            "status": "fail",
                            "message": f"User too far from office ({distance_meters:.2f} meters). Must be within {LOCATION_RADIUS_METERS}m."
                        }, status=400)

                    now_ist = timezone.localtime(timezone.now(), IST)
                    today = now_ist.date()
                    now_time = now_ist.time()

                    existing = Attendance.objects.filter(email=person.email, date=today).first()
                    if existing:
                        if existing.check_out:
                            msg = f"Attendance already marked for today ({person.fullname})"
                        else:
                            existing.check_out = now_time
                            existing.latitude = latitude
                            existing.longitude = longitude
                            existing.location_type = "office"
                            existing.save()
                            msg = f"Office check-out marked for {person.fullname}"
                        os.remove(tmp_path)
                        return JsonResponse({"status": "success", "message": msg})

                    # Check if deadline applies (Mon-Sat, not holiday)
                    enforce_deadline = True
                    if today.weekday() == 6:
                        enforce_deadline = False
                    else:
                        from accounts.models import Holiday
                        if Holiday.objects.filter(date=today).exists():
                            enforce_deadline = False

                    # Block before 7 AM
                    if now_time < CHECK_IN_START:
                        os.remove(tmp_path)
                        return JsonResponse({
                            "status": "fail",
                            "message": "Check-in opens at 07:00 AM IST. Please try after 07:00."
                        }, status=400)

                    # Mark absent if first attempt after deadline
                    if enforce_deadline and now_time > CHECK_IN_DEADLINE:
                        AbsentEmployeeDetails.objects.get_or_create(email=person.email, date=today)
                        os.remove(tmp_path)
                        return JsonResponse({
                            "status": "fail",
                            "message": "Late first attempt. Marked absent for today as no check-in before 10:45 AM IST."
                        }, status=400)

                    # Otherwise, mark attendance
                    obj, created = Attendance.objects.get_or_create(
                        email=person.email,
                        date=today,
                        defaults={
                            "check_in": now_time,
                            "latitude": latitude,
                            "longitude": longitude,
                            "location_type": "office",
                            "role": person.__class__.__name__  # store role name (Employee, HR, etc.)
                        }
                    )

                    if created:
                        msg = f"Office check-in marked for {person.fullname}"
                    else:
                        if obj.check_out:
                            msg = f"Attendance already marked for today ({person.fullname})"
                        else:
                            obj.check_out = now_time
                            obj.latitude = latitude
                            obj.longitude = longitude
                            obj.location_type = "office"
                            obj.save()
                            msg = f"Office check-out marked for {person.fullname}"

                    os.remove(tmp_path)
                    return JsonResponse({"status": "success", "message": msg})

            except Exception as err:
                print(f"Error processing {person.email}: {err}")
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
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")

        # Convert if provided
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
        now_ist = timezone.localtime(timezone.now(), IST)
        today = now_ist.date()
        current_time = now_ist.time()

        if current_time < CHECK_IN_START:
            os.remove(tmp_path)
            return JsonResponse({
                "status": "fail",
                "message": "Check-in opens at 07:00 AM IST. Please try after 07:00."
            }, status=400)

        # Loop through all user types
        people = get_all_users_with_photos()
        for person in people:
            if not person.profile_picture:
                continue

            try:
                response = requests.get(person.profile_picture, timeout=10)
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
                    now_ist = timezone.localtime(timezone.now(), IST)
                    today = now_ist.date()
                    now_time = now_ist.time()

                    existing = Attendance.objects.filter(email=person.email, date=today).first()
                    if existing:
                        if existing.check_out:
                            msg = f"Attendance already marked for today ({person.fullname})"
                        else:
                            existing.check_out = now_time
                            existing.longitude = longitude
                            existing.location_type = "work"
                            existing.save()
                            msg = f"Work from home check-out marked for {person.fullname}"
                        os.remove(tmp_path)
                        return JsonResponse({"status": "success", "message": msg})

                    enforce_deadline = True
                    if today.weekday() == 6:
                        enforce_deadline = False
                    else:
                        from accounts.models import Holiday
                        if Holiday.objects.filter(date=today).exists():
                            enforce_deadline = False

                    if now_time < CHECK_IN_START:
                        os.remove(tmp_path)
                        return JsonResponse({
                            "status": "fail",
                            "message": "Check-in opens at 07:00 AM IST. Please try after 07:00."
                        }, status=400)

                    if enforce_deadline and now_time > CHECK_IN_DEADLINE:
                        AbsentEmployeeDetails.objects.get_or_create(email=person.email, date=today)
                        os.remove(tmp_path)
                        return JsonResponse({
                            "status": "fail",
                            "message": "Late first attempt. Marked absent for today as no check-in before 10:45 AM IST."
                        }, status=400)

                    obj, created = Attendance.objects.get_or_create(
                        email=person.email,
                        date=today,
                        defaults={
                            "check_in": now_time,
                            "latitude": latitude,
                            "longitude": longitude,
                            "location_type": "work",
                            "role": person.__class__.__name__
                        }
                    )

                    if created:
                        msg = f"Work from home check-in marked for {person.fullname}"
                    else:
                        if obj.check_out:
                            msg = f"Attendance already marked for today ({person.fullname})"
                        else:
                            obj.check_out = now_time
                            obj.longitude = longitude
                            obj.location_type = "work"
                            obj.save()
                            msg = f"Work from home check-out marked for {person.fullname}"

                    os.remove(tmp_path)
                    return JsonResponse({"status": "success", "message": msg})

            except Exception as err:
                print(f"Error processing {person.email}: {err}")
                continue

        os.remove(tmp_path)
        return JsonResponse({"status": "fail", "message": "No match found"}, status=404)

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_absent_employees(request):
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
                    # Mark as absent (idempotent)
                    _, created = AbsentEmployeeDetails.objects.get_or_create(
                        email=emp.email,
                        date=today
                    )
                    if created:
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
        'logo_url': getattr(settings, 'LOGO_URL', ''),
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
    # Check if pisa_status_minio has an error by checking if it has the err attribute
    if hasattr(pisa_status_minio, 'err'):
        err_value = getattr(pisa_status_minio, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    # Check if pisa_status_email has an error by checking if it has the err attribute
    if hasattr(pisa_status_email, 'err'):
        err_value = getattr(pisa_status_email, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "appointment_letter.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        minio_conf = settings.MINIO_STORAGE
        protocol = "https" if minio_conf.get("USE_SSL", False) else "http"
        s3 = boto3.client(
            's3',
            endpoint_url=f"{protocol}://{minio_conf['ENDPOINT']}",
            aws_access_key_id=minio_conf['ACCESS_KEY'],
            aws_secret_access_key=minio_conf['SECRET_KEY']
        )

        bucket_name = minio_conf['BUCKET_NAME']
        s3.upload_fileobj(
            pdf_minio,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        file_url = f"{protocol}://{minio_conf['ENDPOINT']}/{bucket_name}/{object_name}"

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
    # Check if pisa_status_minio has an error by checking if it has the err attribute
    if hasattr(pisa_status_minio, 'err'):
        err_value = getattr(pisa_status_minio, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    # Check if pisa_status_email has an error by checking if it has the err attribute
    if hasattr(pisa_status_email, 'err'):
        err_value = getattr(pisa_status_email, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "offer_letter.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        minio_conf = settings.MINIO_STORAGE
        protocol = "https" if minio_conf.get("USE_SSL", False) else "http"
        s3 = boto3.client(
            's3',
            endpoint_url=f"{protocol}://{minio_conf['ENDPOINT']}",
            aws_access_key_id=minio_conf['ACCESS_KEY'],
            aws_secret_access_key=minio_conf['SECRET_KEY']
        )

        bucket_name = minio_conf['BUCKET_NAME']
        s3.upload_fileobj(
            pdf_minio,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        file_url = f"{protocol}://{minio_conf['ENDPOINT']}/{bucket_name}/{object_name}"

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

    pisa_status_minio = pisa.CreatePDF(html, dest=pdf_minio, encoding='UTF-8')
    # Check if pisa_status_minio has an error by checking if it has the err attribute
    if hasattr(pisa_status_minio, 'err'):
        err_value = getattr(pisa_status_minio, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    # Check if pisa_status_email has an error by checking if it has the err attribute
    if hasattr(pisa_status_email, 'err'):
        err_value = getattr(pisa_status_email, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "releaving_letter.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        minio_conf = settings.MINIO_STORAGE
        protocol = "https" if minio_conf.get("USE_SSL", False) else "http"
        s3 = boto3.client(
            's3',
            endpoint_url=f"{protocol}://{minio_conf['ENDPOINT']}",
            aws_access_key_id=minio_conf['ACCESS_KEY'],
            aws_secret_access_key=minio_conf['SECRET_KEY']
        )
        bucket_name = minio_conf['BUCKET_NAME']
        s3.upload_fileobj(pdf_minio, bucket_name, object_name, ExtraArgs={'ContentType': 'application/pdf'})

        file_url = f"{protocol}://{minio_conf['ENDPOINT']}/{bucket_name}/{object_name}"

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
    # Check if pisa_status_minio has an error by checking if it has the err attribute
    if hasattr(pisa_status_minio, 'err'):
        err_value = getattr(pisa_status_minio, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (MinIO)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_minio.seek(0)

    pisa_status_email = pisa.CreatePDF(html, dest=pdf_email, encoding='UTF-8')
    # Check if pisa_status_email has an error by checking if it has the err attribute
    if hasattr(pisa_status_email, 'err'):
        err_value = getattr(pisa_status_email, 'err', None)
        if err_value:
            return Response({"error": "PDF generation failed (Email)"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    pdf_email.seek(0)

    # -------------------- Upload to MinIO -------------------- #
    filename = "bonafide_crt.pdf"
    object_name = f"documents/{folder_name}/{filename}"

    try:
        minio_conf = settings.MINIO_STORAGE
        protocol = "https" if minio_conf.get("USE_SSL", False) else "http"
        s3 = boto3.client(
            's3',
            endpoint_url=f"{protocol}://{minio_conf['ENDPOINT']}",
            aws_access_key_id=minio_conf['ACCESS_KEY'],
            aws_secret_access_key=minio_conf['SECRET_KEY']
        )

        bucket_name = minio_conf['BUCKET_NAME']
        s3.upload_fileobj(
            pdf_minio,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        file_url = f"{protocol}://{minio_conf['ENDPOINT']}/{bucket_name}/{object_name}"

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
                # Fixed: Check if item is a dict before accessing get method
                if not isinstance(item, dict):
                    continue
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
            # Fixed: Check if data is a dict before accessing get method
            if not isinstance(data, dict):
                return Response({"detail": "Invalid data format"}, status=status.HTTP_400_BAD_REQUEST)
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


# ===== Attendance Correction Requests =====
@api_view(['POST'])
@permission_classes([AllowAny])
def raise_attendance_request(request):
    """
    Employee raises a request to change Absent to Present for a given date.
    Body: { "email": "user@x.com", "date": "YYYY-MM-DD", "reason": "..." }
    One request per (email, date).
    """
    email = request.data.get('email')
    date_str = request.data.get('date')
    reason = request.data.get('reason')

    if not email or not date_str or not reason:
        return Response({"error": "email, date, and reason are required"}, status=status.HTTP_400_BAD_REQUEST)

    user = get_object_or_404(User, email=email)
    try:
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

    obj, created = RaiseRequestAttendance.objects.get_or_create(
        email=user,
        date=req_date,
        defaults={
            'reason': reason,
        }
    )

    if not created:
        # Update reason if re-submitted while pending/rejected
        obj.reason = reason or obj.reason
        obj.status = obj.status or 'Pending'
        obj.save()

    return Response({
        "message": "Attendance request submitted",
        "id": obj.id,
        "email": email,
        "date": str(obj.date),
        "status": obj.status
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_attendance_requests(request):
    """
    List correction requests. Optional filters: status, email
    """
    qs = RaiseRequestAttendance.objects.all().order_by('-created_at')
    status_filter = request.GET.get('status')
    email_filter = request.GET.get('email')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if email_filter:
        qs = qs.filter(email__email=email_filter)

    data = [
        {
            'id': r.id,
            'email': r.email.email,
            'date': str(r.date),
            'reason': r.reason,
            'manager_remark': r.manager_remark,
            'status': r.status,
            'reviewed_by': r.reviewed_by.email if r.reviewed_by else None,
            'created_at': r.created_at.isoformat(),
            'updated_at': r.updated_at.isoformat(),
        }
        for r in qs
    ]
    return Response(data)


@api_view(['PATCH'])
@permission_classes([AllowAny])
def review_attendance_request(request, pk):
    """
    Manager reviews a request.
    Body: { "approved": true/false, "manager_remark": "...", "reviewer_email": "manager@x.com" }
    On approve: remove AbsentEmployeeDetails(email,date) and ensure Attendance exists (create if needed).
    """
    approved = request.data.get('approved')
    manager_remark = request.data.get('manager_remark', '')
    reviewer_email = request.data.get('reviewer_email')

    if approved is None or reviewer_email is None:
        return Response({"error": "approved and reviewer_email are required"}, status=status.HTTP_400_BAD_REQUEST)

    req = get_object_or_404(RaiseRequestAttendance, id=pk)
    reviewer = get_object_or_404(User, email=reviewer_email)

    req.reviewed_by = reviewer
    req.manager_remark = manager_remark
    req.status = 'Approved' if approved else 'Rejected'
    req.save()

    if approved:
        # Remove absent record if present
        AbsentEmployeeDetails.objects.filter(email=req.email, date=req.date).delete()

        # Ensure an attendance record exists; if not, create with check_in at deadline
        from .constants import CHECK_IN_DEADLINE
        Attendance.objects.get_or_create(
            email=req.email,
            date=req.date,
            defaults={
                'check_in': CHECK_IN_DEADLINE,
                'location_type': 'office',
                'latitude': OFFICE_LAT,
                'longitude': OFFICE_LON
            }
        )

    return Response({
        "message": "Request reviewed",
        "id": req.id,
        "status": req.status
    })


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
    # Only prevent reapplication if there's a pending or approved resignation
    # Rejected resignations (manager or HR) should allow new applications
    existing_releaved = ReleavedEmployee.objects.filter(email=email).first()
    if existing_releaved:
        # If HR already approved, final offboarding is handled in HR approve flow.
        if existing_releaved.hr_approved == 'Approved':
            return Response({
                "message": f"{email} already HR-approved. Final offboarding is completed during HR approval process.",
            }, status=status.HTTP_200_OK)

        # If there's a pending flow, prevent duplicate submissions
        if existing_releaved.manager_approved == 'Pending' or existing_releaved.manager_approved == 'Approved' or existing_releaved.hr_approved == 'Pending':
            return Response({
                "message": f"{email} resignation is in progress.",
                "manager_approved": existing_releaved.manager_approved,
                "hr_approved": existing_releaved.hr_approved
            }, status=status.HTTP_400_BAD_REQUEST)

        # If previously rejected at any stage, allow re-application by creating a new record

    # Create ReleavedEmployee with email as string
    data = {
        'email': email,  # Store email as string, not User FK
        'fullname': employee.fullname,
        'phone': employee.phone,
        # Fixed: Use getattr to avoid type checking issues
        'role': getattr(user, 'role', ''),
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
        'manager_approved': 'Pending',  # Stage 1: Pending manager approval
        'manager_description': None,
        'hr_approved': None,  # Stage 2: Not yet reached
        'hr_description': None,
        'applied_at': timezone.now(),
    }

    releaved = ReleavedEmployee.objects.create(**data)

    # Fixed: Use pk instead of id for ReleavedEmployee
    return Response({"message": f"{email} transferred to ReleavedEmployee.", "id": releaved.pk}, status=status.HTTP_201_CREATED)



@csrf_exempt
@permission_classes([AllowAny])
@api_view(['PATCH'])
def approve_releaved(request, pk):
    """
    Two-stage approval for releaved employee:
    Stage 1 (Manager): 
        - Update manager_approved ('Approved' or 'Rejected')
        - Update manager_description
        - If approved, set hr_approved to 'Pending'
    Stage 2 (HR):
        - Update hr_approved ('Approved' or 'Rejected')
        - Update hr_description
        - If approved, delete Employee, EmployeeDetails, and User
    - Send email notifications
    """
    approval_stage = request.data.get('approval_stage')  # 'manager' or 'hr'
    approved = request.data.get('approved')  # 'Approved' or 'Rejected'
    description = request.data.get('description', '')

    if approval_stage not in ['manager', 'hr']:
        return Response({"error": "approval_stage must be 'manager' or 'hr'."}, status=status.HTTP_400_BAD_REQUEST)
    
    if approved not in ['Approved', 'Rejected']:
        return Response({"error": "approved must be 'Approved' or 'Rejected'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Use ID lookup instead of email
        releaved = ReleavedEmployee.objects.get(id=pk)
        email = releaved.email  # Get email for notifications
    except ReleavedEmployee.DoesNotExist:
        return Response({"error": "ReleavedEmployee not found."}, status=status.HTTP_404_NOT_FOUND)

    # Prepare email content variables
    employee_name = releaved.fullname or email
    designation = releaved.designation or "Employee"
    offboarding_date_ist = timezone.localtime(releaved.applied_at, IST) if releaved.applied_at else None
    offboarding_date = offboarding_date_ist.strftime('%B %d, %Y at %I:%M %p') if offboarding_date_ist else 'N/A'
    offboarding_date_plain = offboarding_date_ist.strftime('%Y-%m-%d %H:%M:%S IST') if offboarding_date_ist else 'N/A'

    # ============ STAGE 1: Manager Approval ============
    if approval_stage == 'manager':
        if releaved.manager_approved in ['Approved', 'Rejected']:
            return Response({
                "error": f"Manager has already {releaved.manager_approved.lower()} this resignation."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update manager approval fields
        releaved.manager_approved = approved
        releaved.manager_description = description
        
        if approved == 'Approved':
            # Move to Stage 2: Set HR approval as Pending
            releaved.hr_approved = 'Pending'
            releaved.save()
            
            # Send email to employee about manager approval
            subject = "Resignation - Manager Approved - Awaiting HR Approval"
            html_message = render_to_string('emails/resignation_manager_approved.html', {
                'employee_name': employee_name,
                'designation': designation,
                'email': email,
                'reason_for_resignation': releaved.reason_for_resignation,
                'description': description,
                'current_year': datetime.now().year
            })
            
            plain_message = f"""Dear {employee_name},

Your resignation has been approved by your manager and is now pending HR approval.

Employee Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

Manager Comments: {description if description else 'No additional comments.'}

The HR department will review your resignation shortly.

Best regards,
HR Department
Global Tech Software Solutions
"""
            
            try:
                Thread(target=send_email_async, args=(subject, plain_message, html_message, email)).start()
            except Exception as e:
                print(f"Failed to send manager approval email to {email}: {str(e)}")
            
            return Response({
                "message": f"Manager approved resignation for {email}. Now pending HR approval. Email notification sent."
            }, status=status.HTTP_200_OK)
        
        else:  # Manager Rejected
            # Update the record to show it was rejected but keep it for audit purposes
            releaved.manager_approved = 'Rejected'
            releaved.manager_description = description
            releaved.save()
            
            # Send rejection email
            subject = "Resignation Request - Manager Rejected"
            html_message = render_to_string('emails/resignation_manager_rejected.html', {
                'employee_name': employee_name,
                'designation': designation,
                'email': email,
                'reason_for_resignation': releaved.reason_for_resignation,
                'description': description,
                'current_year': datetime.now().year
            })
            
            plain_message = f"""Dear {employee_name},

Your resignation has been rejected by your manager.

Employee Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

Manager Comments: {description if description else 'Please contact your manager for further discussion.'}

Best regards,
HR Department
Global Tech Software Solutions
"""
            
            try:
                Thread(target=send_email_async, args=(subject, plain_message, html_message, email)).start()
            except Exception as e:
                print(f"Failed to send manager rejection email to {email}: {str(e)}")
            
            return Response({
                "message": f"Manager rejected resignation for {email}. Rejection email sent. Employee can now submit a new application."
            }, status=status.HTTP_200_OK)
    
    # ============ STAGE 2: HR Approval ============
    elif approval_stage == 'hr':
        if releaved.manager_approved != 'Approved':
            return Response({
                "error": "Cannot process HR approval. Manager approval is required first."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if releaved.hr_approved in ['Approved', 'Rejected']:
            return Response({
                "error": f"HR has already {releaved.hr_approved.lower()} this resignation."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update HR approval fields
        releaved.hr_approved = approved
        releaved.hr_description = description
        
        # Set ready_to_releve flag to True only when HR approves
        if approved == 'Approved':
            releaved.ready_to_releve = True
        
        releaved.save()
        
        if approved == 'Approved':
            # Set final offboarding timestamp now
            releaved.offboarded_datetime = timezone.now()
            releaved.save(update_fields=["ready_to_releve", "hr_approved", "hr_description", "offboarded_datetime"])
            # Send approval email to employee
            subject = "Resignation Approved - Offboarding Confirmation"
            
            offboarding_date_ist = timezone.localtime(releaved.offboarded_datetime, IST)
            offboarding_date = offboarding_date_ist.strftime('%B %d, %Y at %I:%M %p')
            offboarding_date_plain = offboarding_date_ist.strftime('%Y-%m-%d %H:%M:%S IST')
            
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

Your resignation has been fully approved by both manager and HR.

Employee Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
- Offboarding Date: {offboarding_date_plain}
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

HR Comments: {description if description else 'Thank you for your contributions to the organization. We wish you all the best in your future endeavors.'}

Best regards,
HR Department
Global Tech Software Solutions
"""
            
            try:
                Thread(target=send_email_async, args=(subject, plain_message, html_message, email)).start()
            except Exception as e:
                print(f"Failed to send HR approval email to {email}: {str(e)}")
            
            # Send notification to all CEOs and Managers
            try:
                from accounts.models import CEO, Manager
                
                ceos = CEO.objects.all()
                managers = Manager.objects.all()
                
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

Approval Status: Approved by Manager and HR

Manager Comments: {releaved.manager_description or 'N/A'}
HR Comments: {description if description else 'N/A'}

This is an automated notification from the HR system.

Best regards,
HR Department
Global Tech Software Solutions
"""
                
                leadership_html_message = render_to_string('emails/employee_offboarded_leadership.html', {
                    'employee_name': employee_name,
                    'designation': designation,
                    'email': email,
                    'department': releaved.department or 'N/A',
                    'offboarding_date': offboarding_date,
                    'reason_for_resignation': releaved.reason_for_resignation,
                    'description': f"Manager: {releaved.manager_description or 'N/A'}\nHR: {description or 'N/A'}",
                    'current_year': datetime.now().year
                })
                
                # Send to CEOs
                for ceo in ceos:
                    try:
                        Thread(target=send_email_async, args=(leadership_subject, leadership_plain_message, leadership_html_message, ceo.email.email)).start()
                    except Exception as e:
                        print(f"Failed to send offboarding notification to CEO {ceo.email.email}: {str(e)}")
                
                # Send to Managers
                for manager in managers:
                    try:
                        Thread(target=send_email_async, args=(leadership_subject, leadership_plain_message, leadership_html_message, manager.email.email)).start()
                    except Exception as e:
                        print(f"Failed to send offboarding notification to Manager {manager.email.email}: {str(e)}")
                
                print(f"Offboarding notifications sent to {ceos.count()} CEOs and {managers.count()} Managers")
            
            except Exception as e:
                print(f"Failed to send offboarding notifications to leadership: {str(e)}")
            
            # Delete Employee, EmployeeDetails, and User
            try:
                user = User.objects.filter(email=email).first()
                if user:
                    Employee.objects.filter(email=user).delete()
                    EmployeeDetails.objects.filter(email=user).delete()
                    user.delete()
            except Exception as e:
                return Response({"error": f"Failed to delete related records: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response({
                "message": f"HR approved resignation for {email}. Employee offboarded successfully. Notifications sent.",
                "offboarded_datetime": releaved.offboarded_datetime
            }, status=status.HTTP_200_OK)
        
        else:  # HR Rejected
            # Update the record to show it was rejected but keep it for audit purposes
            releaved.hr_approved = 'Rejected'
            releaved.hr_description = description
            releaved.save()
            
            # Send rejection email
            subject = "Resignation Request - HR Rejected"
            html_message = render_to_string('emails/resignation_hr_rejected.html', {
                'employee_name': employee_name,
                'designation': designation,
                'email': email,
                'reason_for_resignation': releaved.reason_for_resignation,
                'description': description,
                'current_year': datetime.now().year
            })
            
            plain_message = f"""Dear {employee_name},

Your resignation has been put on hold by HR.

Employee Details:
- Name: {employee_name}
- Designation: {designation}
- Email: {email}
{f'- Resignation Reason: {releaved.reason_for_resignation}' if releaved.reason_for_resignation else ''}

HR Comments: {description if description else 'Please contact HR for further discussion.'}

Best regards,
HR Department
Global Tech Software Solutions
"""
            
            try:
                Thread(target=send_email_async, args=(subject, plain_message, html_message, email)).start()
            except Exception as e:
                print(f"Failed to send HR rejection email to {email}: {str(e)}")
            
            return Response({
                "message": f"HR rejected resignation for {email}. Rejection email sent. Employee can now submit a new application."
            }, status=status.HTTP_200_OK)


# (Removed separate endpoint for setting offboarded_datetime per user request)


@api_view(['GET'])
def list_releaved_employees(request):
    """
    Get all relieved employees with optional filtering
    Query params:
    - manager_approved: Filter by manager approval status ('Pending', 'Approved', 'Rejected')
    - hr_approved: Filter by HR approval status ('Pending', 'Approved', 'Rejected')
    - department: Filter by department
    - designation: Filter by designation
    """
    releaved_employees = ReleavedEmployee.objects.all().order_by('-applied_at')
    
    # Apply filters for manager approval
    manager_approved_filter = request.GET.get('manager_approved')
    if manager_approved_filter:
        releaved_employees = releaved_employees.filter(manager_approved=manager_approved_filter)
    
    # Apply filters for HR approval
    hr_approved_filter = request.GET.get('hr_approved')
    if hr_approved_filter:
        releaved_employees = releaved_employees.filter(hr_approved=hr_approved_filter)
    
    department_filter = request.GET.get('department')
    if department_filter:
        releaved_employees = releaved_employees.filter(department__icontains=department_filter)
    
    designation_filter = request.GET.get('designation')
    if designation_filter:
        releaved_employees = releaved_employees.filter(designation__icontains=designation_filter)
    
    serializer = ReleavedEmployeeSerializer(releaved_employees, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_releaved_employee(request, pk):
    """
    Get single relieved employee by ID
    Returns full details including resignation reason and approval status
    """
    try:
        releaved = ReleavedEmployee.objects.get(id=pk)
        serializer = ReleavedEmployeeSerializer(releaved)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except ReleavedEmployee.DoesNotExist:
        return Response({
            "error": "Relieved employee not found.",
            "id": pk
        }, status=status.HTTP_404_NOT_FOUND)


from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import PettyCash
from .serializers import PettyCashSerializer


@api_view(['GET'])
def list_pettycash(request):
    """List all petty cash records"""
    records = PettyCash.objects.all().order_by('-created_at')
    serializer = PettyCashSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def create_pettycash(request):
    """Create a new petty cash record"""
    serializer = PettyCashSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def get_pettycash(request, id):
    """Retrieve a specific petty cash record by ID"""
    try:
        record = PettyCash.objects.get(id=id)
    except PettyCash.DoesNotExist:
        return Response({'error': 'Petty cash record not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = PettyCashSerializer(record)
    return Response(serializer.data)


@api_view(['PATCH'])
def update_pettycash(request, id):
    """Update (partial) a petty cash record"""
    try:
        record = PettyCash.objects.get(id=id)
    except PettyCash.DoesNotExist:
        return Response({'error': 'Petty cash record not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = PettyCashSerializer(record, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
def delete_pettycash(request, id):
    """Delete a petty cash record"""
    try:
        record = PettyCash.objects.get(id=id)
    except PettyCash.DoesNotExist:
        return Response({'error': 'Petty cash record not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    record.delete()
    return Response({'message': 'Petty cash record deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)
