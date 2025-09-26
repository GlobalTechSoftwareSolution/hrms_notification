import os
import json
import base64
import pytz
import numpy as np
import cv2
from io import BytesIO
from PIL import Image

from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth import authenticate, get_user_model
# from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date

from django.db.models import Q

from rest_framework import status, viewsets, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes

# Models
from .models import (
    User, CEO, HR, Manager, Employee, Attendance, Admin,
    Leave, Payroll, TaskTable, Project, Notice, Report
)

# Serializers
from .serializers import (
    UserSerializer, CEOSerializer, HRSerializer, ManagerSerializer,
    EmployeeSerializer, SuperUserCreateSerializer, UserRegistrationSerializer,
    AdminSerializer, ReportSerializer, RegisterSerializer
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


# =====================
# Helper: get email by username (partial match)
# =====================
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


# =====================
# Check if email exists
# =====================
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


# =====================
# Mark attendance by email
# =====================
IST = pytz.timezone("Asia/Kolkata")

def mark_attendance_by_email(email_str):
    if not is_email_exists(email_str):
        print(f"[mark_attendance_by_email] Email {email_str} not found. Attendance not marked.")
        return None

    today = timezone.localdate()
    now = timezone.now().astimezone(IST)   # force IST
    print(f"[mark_attendance_by_email] Processing attendance for {email_str} on {today} at {now}")

    try:
        user_instance = User.objects.get(email=email_str)
    except User.DoesNotExist:
        print(f"[mark_attendance_by_email] User instance not found for {email_str}")
        return None

    try:
        attendance = Attendance.objects.get(email=user_instance, date=today)
        if attendance.check_out is None:
            attendance.check_out = now
            attendance.save()
            print(f"[mark_attendance_by_email] Updated check_out for {email_str} at {now}")
    except Attendance.DoesNotExist:
        try:
            attendance = Attendance.objects.create(
                email=user_instance,
                date=today,
                check_in=now
            )
            print(f"[mark_attendance_by_email] Created new attendance record for {email_str} at {now}")
        except Exception as e:
            print(f"[mark_attendance_by_email ERROR] Failed to save attendance for {email_str}: {e}")
            return None

    return attendance


# =====================
# Face recognition API
# =====================
KNOWN_FACES_DIR = os.path.join(settings.BASE_DIR, "images")
known_face_names = []
known_face_descriptors = []

# Initialize ORB detector globally to reuse
orb = cv2.ORB_create()

# Load known faces and compute ORB descriptors
if os.path.exists(KNOWN_FACES_DIR):
    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.lower().endswith(('.jpg', '.png')):
            image_path = os.path.join(KNOWN_FACES_DIR, filename)
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                kp, des = orb.detectAndCompute(img, None)
                if des is not None:
                    known_face_descriptors.append(des)
                    username, _ = os.path.splitext(filename)
                    known_face_names.append(username.lower())
                    print(f"Loaded known face: {username.lower()}")
else:
    print(f"[WARNING] Known faces directory {KNOWN_FACES_DIR} not found. Skipping face loading.")


# Face detector Haar cascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

@api_view(['POST'])
@permission_classes([AllowAny])
def recognize_face(request):
    data = request.data
    image_data = data.get("image", "")
    if not image_data:
        return JsonResponse({"error": "No image data provided"}, status=400)

    if "," in image_data:
        image_data = image_data.split(",")[1]

    img_bytes = base64.b64decode(image_data)
    img = Image.open(BytesIO(img_bytes)).convert('RGB')
    img_np = np.array(img)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        return JsonResponse({"username": "No face detected"}, status=200)

    x, y, w, h = faces[0]
    face_roi = gray[y:y+h, x:x+w]

    kp2, des2 = orb.detectAndCompute(face_roi, None)
    if des2 is None:
        return JsonResponse({"username": "Unknown", "reason": "No features detected in input face"}, status=200)

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    best_match = None
    best_avg_distance = 100

    # Match input face with all known faces
    for des_known, name in zip(known_face_descriptors, known_face_names):
        matches = bf.match(des_known, des2)
        if not matches:
            continue
        matches = sorted(matches, key=lambda m: m.distance)
        avg_distance = sum(m.distance for m in matches) / len(matches)
        if avg_distance < best_avg_distance:
            best_avg_distance = avg_distance
            best_match = name

    threshold = 45  # Tune this threshold based on your tests

    if best_match and best_avg_distance < threshold:
        username = best_match
        email = get_email_by_username(username)  # Your existing function
        confidence = round((1 - (best_avg_distance / threshold)) * 100, 2)
        attendance = mark_attendance_by_email(email)  # Your existing function
    else:
        username = "Unknown"
        email = None
        confidence = 0
        attendance = None

    return JsonResponse({
        "username": username,
        "email": email,
        "confidence": f"{confidence}%" if email else "",
        "check_in": str(attendance.check_in) if attendance else "",
        "check_out": str(attendance.check_out) if attendance else ""
    })


# =====================
# Today attendance view
# =====================
def today_attendance(request):
    today = timezone.localdate()
    attendances = Attendance.objects.filter(date=today)

    data = [
        {
            "email": att.email.email,
            "date": att.date,
            "check_in": str(att.check_in) if att.check_in else "",
            "check_out": str(att.check_out) if att.check_out else ""
        }
        for att in attendances
    ]

    return JsonResponse({"attendances": data})


# Helper function to handle PUT
def handle_put(request, ModelClass, SerializerClass):
    try:
        data = json.loads(request.body)
        email = data.get("email")
        if not email:
            return JsonResponse({"error": "Email field is required"}, status=400)
        instance = ModelClass.objects.get(email=email)
    except ModelClass.DoesNotExist:
        return JsonResponse({"error": f"{ModelClass._name_} not found"}, status=404)
    serializer = SerializerClass(instance, data=data, partial=True)  # partial=True allows partial updates
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
        print(f"Deleted {ModelClass._name_} record with email {email}")
        
        # Also delete corresponding User record
        from accounts.models import User  # import User model
        try:
            user = User.objects.get(email=email)
            user.delete()
            print(f"Deleted User record with email {email}")
        except User.DoesNotExist:
            print(f"No User record found to delete for email {email}")
        
        return JsonResponse({"message": f"{ModelClass._name_} and User deleted successfully"})
    except ModelClass.DoesNotExist:
        return JsonResponse({"error": f"{ModelClass._name_} not found"}, status=404)


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


# ----------------------------
# List all tasks
# ----------------------------
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


# ----------------------------
# Get single task by id
# ----------------------------
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


# ----------------------------
# Update task by id
# ----------------------------
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


# ----------------------------
# Delete task by id
# ----------------------------
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
        email_str = data.get("email")
        email_user = None
        if email_str:
            # Try to get User instance, or else leave null
            email_user = User.objects.filter(email=email_str).first()

        notice = Notice.objects.create(
            title=data.get("title"),
            message=data.get("message"),
            email=email_user,
            important=data.get("important", False),
            # If you want to handle file attachments, add logic here
        )
        return JsonResponse({"id": notice.id, "title": notice.title})

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
        # You can add update logic for valid_until or attachment if needed
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


from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "ok"})

from django.views.decorators.http import require_GET
from django.http import JsonResponse

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
    
from rest_framework import generics
from .models import MyUser
from .serializers import MyUserSerializer

class MyUserCreateView(generics.CreateAPIView):
    queryset = MyUser.objects.all()
    serializer_class = MyUserSerializer


# import cv2
# import numpy as np
# from django.utils.timezone import now
# from rest_framework.response import Response
# from rest_framework.decorators import api_view
# from .models import MyUser, Attendee
# from django.core.files.storage import default_storage

# @api_view(['POST'])
# def face_scan_checkin_checkout(request):
#     try:
#         uploaded_file = request.FILES.get('image')
#         if not uploaded_file:
#             return Response({"error": "No image uploaded"}, status=400)

#         file_bytes = np.frombuffer(uploaded_file.read(), np.uint8)
#         uploaded_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
#         gray_uploaded = cv2.cvtColor(uploaded_img, cv2.COLOR_BGR2GRAY)

#         face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
#         faces = face_cascade.detectMultiScale(gray_uploaded, scaleFactor=1.1, minNeighbors=5)
#         if len(faces) == 0:
#             return Response({"error": "No face detected in image"}, status=400)

#         x, y, w, h = faces[0]
#         uploaded_face = gray_uploaded[y:y+h, x:x+w]

#         users = MyUser.objects.all()
#         for user in users:
#             if not user.profile:
#                 continue

#             try:
#                 profile_path = default_storage.path(user.profile.name)
#                 profile_img = cv2.imread(profile_path)
#                 if profile_img is None:
#                     continue
#                 gray_profile = cv2.cvtColor(profile_img, cv2.COLOR_BGR2GRAY)

#                 profile_faces = face_cascade.detectMultiScale(gray_profile, scaleFactor=1.1, minNeighbors=5)
#                 if len(profile_faces) == 0:
#                     continue

#                 px, py, pw, ph = profile_faces[0]
#                 profile_face = gray_profile[py:py+ph, px:px+pw]

#                 resized_uploaded = cv2.resize(uploaded_face, (pw, ph))
#                 res = cv2.matchTemplate(profile_face, resized_uploaded, cv2.TM_CCOEFF_NORMED)
#                 _, max_val, _, _ = cv2.minMaxLoc(res)

#                 if max_val > 0.6:
#                     # Fetch the user's attendance record
#                     attendance = Attendee.objects.filter(user_email=user).first()

#                     if attendance is None:
#                         # No attendance record exists → create check-in
#                         Attendee.objects.create(user_email=user, check_in=now())
#                         return Response({
#                             "message": "Check-in successful.",
#                             "username": user.username,
#                             "email": user.email
#                         })
#                     elif attendance.check_out is None:
#                         # Checked in but not checked out → allow check-out
#                         attendance.check_out = now()
#                         attendance.save()
#                         return Response({
#                             "message": "Check-out successful.",
#                             "username": user.username,
#                             "email": user.email
#                         })
#                     else:
#                         # Already checked in and checked out → no further action
#                         return Response({
#                             "message": "You have already completed check-in and check-out today.",
#                             "username": user.username,
#                             "email": user.email
#                         })

#             except Exception as e:
#                 print(f"Exception processing user {user.email}: {e}")
#                 continue

#         return Response({"error": "No matching user found"}, status=404)

#     except Exception as e:
#         print("Exception in face_scan_checkin_checkout view:", e)
#         return Response({"error": "Failed to process uploaded image"}, status=400)

# from django.conf import settings
# from django.utils.timezone import now
# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from django.core.files.storage import default_storage
# import cv2
# import numpy as np
# from PIL import Image
# import os
# from .models import Attendee, Admin, HR, Manager, Employee, CEO

# # List of all user models
# USER_MODELS = [Admin, HR, Manager, Employee, CEO]

# def load_image_cv2(image_path):
#     """
#     Safely load an image using Pillow and convert to OpenCV format.
#     Handles JPG, PNG, WEBP, etc.
#     """
#     try:
#         pil_img = Image.open(image_path).convert("RGB")
#         cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
#         return cv_img
#     except Exception as e:
#         print(f"Failed to load image {image_path}: {e}")
#         return None

# @api_view(['POST'])
# def face_scan_checkin_checkout(request):
#     try:
#         uploaded_file = request.FILES.get('image')
#         if not uploaded_file:
#             return Response({"error": "No image uploaded"}, status=400)

#         # Convert uploaded file to OpenCV format
#         file_bytes = np.frombuffer(uploaded_file.read(), np.uint8)
#         uploaded_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
#         if uploaded_img is None:
#             return Response({"error": "Invalid uploaded image"}, status=400)

#         gray_uploaded = cv2.cvtColor(uploaded_img, cv2.COLOR_BGR2GRAY)

#         # Initialize face detector
#         face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
#         faces = face_cascade.detectMultiScale(gray_uploaded, scaleFactor=1.1, minNeighbors=5)
#         if len(faces) == 0:
#             return Response({"error": "No face detected in uploaded image"}, status=400)

#         x, y, w, h = faces[0]
#         uploaded_face = gray_uploaded[y:y+h, x:x+w]

#         # Iterate through all models
#         for model in USER_MODELS:
#             users = model.objects.all()
#             for user in users:
#                 profile_img_field = getattr(user, 'profile_picture', None)
#                 if not profile_img_field:
#                     continue

#                 try:
#                     # Build full file path using MEDIA_ROOT
#                     profile_path = os.path.join(settings.MEDIA_ROOT, profile_img_field.name)
#                     if not os.path.exists(profile_path):
#                         print(f"File not found: {profile_path}")
#                         continue

#                     profile_img = load_image_cv2(profile_path)
#                     if profile_img is None:
#                         continue

#                     gray_profile = cv2.cvtColor(profile_img, cv2.COLOR_BGR2GRAY)
#                     profile_faces = face_cascade.detectMultiScale(gray_profile, scaleFactor=1.1, minNeighbors=5)
#                     if len(profile_faces) == 0:
#                         continue

#                     px, py, pw, ph = profile_faces[0]
#                     profile_face = gray_profile[py:py+ph, px:px+pw]

#                     # Resize uploaded face to match profile face size
#                     resized_uploaded = cv2.resize(uploaded_face, (pw, ph))

#                     # Compare using normalized cross-correlation
#                     res = cv2.matchTemplate(profile_face, resized_uploaded, cv2.TM_CCOEFF_NORMED)
#                     _, max_val, _, _ = cv2.minMaxLoc(res)

#                     # If similarity > threshold, consider a match
#                     if max_val > 0.6:
#                         # Fetch attendance record
#                         attendance = Attendee.objects.filter(user_email=user.email).first()
#                         if attendance is None:
#                             # Check-in
#                             Attendee.objects.create(user_email=user.email, check_in=now())
#                             return Response({
#                                 "message": "Check-in successful",
#                                 "fullname": user.fullname,
#                                 "role": model.__name__,
#                                 "email": user.email
#                             })
#                         elif attendance.check_out is None:
#                             # Check-out
#                             attendance.check_out = now()
#                             attendance.save()
#                             return Response({
#                                 "message": "Check-out successful",
#                                 "fullname": user.fullname,
#                                 "role": model.__name__,
#                                 "email": user.email
#                             })
#                         else:
#                             # Already checked in and out
#                             return Response({
#                                 "message": "You have already completed check-in and check-out today",
#                                 "fullname": user.fullname,
#                                 "role": model.__name__,
#                                 "email": user.email
#                             })

#                 except Exception as e:
#                     print(f"Exception processing user {user.email}: {e}")
#                     continue

#         return Response({"error": "No matching user found"}, status=404)

#     except Exception as e:
#         print("Exception in face_scan_checkin_checkout view:", e)
#         return Response({"error": "Failed to process uploaded image"}, status=400)


# accounts/views.py
import os
import io
import base64
import cv2
import numpy as np
from PIL import Image
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Config
KNOWN_DIR = os.path.join(os.path.dirname(__file__), "known_faces")
HAAR_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(HAAR_PATH)
orb = cv2.ORB_create(nfeatures=500)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

known_descriptors = []

def load_known_faces():
    if not os.path.isdir(KNOWN_DIR):
        os.makedirs(KNOWN_DIR, exist_ok=True)
        return

    for fname in os.listdir(KNOWN_DIR):
        if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        path = os.path.join(KNOWN_DIR, fname)
        base = os.path.splitext(fname)[0]
        parts = base.split("__")   # <-- FIX: was split("")
        username = parts[0] if len(parts) > 0 else base
        email = parts[1] if len(parts) > 1 else ""
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        faces = face_cascade.detectMultiScale(img, 1.1, 4, minSize=(30,30))
        crop = img
        if len(faces) > 0:
            x,y,w,h = faces[0]
            crop = img[y:y+h, x:x+w]
        kp, des = orb.detectAndCompute(crop, None)
        if des is not None:
            known_descriptors.append((des, username.lower(), email.lower()))

load_known_faces()

def decode_base64_image(data_url):
    if "," in data_url:
        _, b64 = data_url.split(",", 1)
    else:
        b64 = data_url
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

@csrf_exempt
def recognize_face(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    # JSON body
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    img_b64 = data.get("image")
    if not img_b64:
        return JsonResponse({"error": "No image provided"}, status=400)

    img_bgr = decode_base64_image(img_b64)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(40,40))
    if len(faces) == 0:
        return JsonResponse({"recognized": False, "message": "No face detected"})

    x,y,w,h = faces[0]
    face_roi = gray[y:y+h, x:x+w]

    kp2, des2 = orb.detectAndCompute(face_roi, None)
    if des2 is None:
        return JsonResponse({"recognized": False, "message": "No features found"})

    best_name, best_email, best_score = None, None, float("inf")
    for des_known, name, email in known_descriptors:
        try:
            matches = bf.match(des_known, des2)
        except:
            continue
        if not matches:
            continue
        avg = sum(m.distance for m in matches) / len(matches)
        if avg < best_score:
            best_score = avg
            best_name, best_email = name, email

    THRESHOLD = 50
    if best_name and best_score < THRESHOLD:
        return JsonResponse({
            "recognized": True,
            "username": best_name,
            "email": best_email,
            "score": float(best_score),
        })
    else:
        return JsonResponse({
            "recognized": False,
            "message": "Unknown person",
            "best_guess": best_name or "",
            "score": float(best_score) if best_name else None,
        })
