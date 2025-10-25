from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime, time


# ------------------- USER -------------------
class UserManager(BaseUserManager):
    def create_user(self, email, role, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, role='CEO', password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, role, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(primary_key=True, max_length=254)
    role = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['role']

    objects = UserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"


# ------------------- DEPARTMENT -------------------
class Department(models.Model):
    department_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.department_name


# ------------------- EMPLOYEE TYPES -------------------
class HR(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    age = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    qualification = models.CharField(max_length=255, null=True, blank=True)
    skills = models.TextField(null=True, blank=True)
    profile_picture = models.URLField(null=True, blank=True)

    def __str__(self):
        return f"{self.fullname} (HR)"


class CEO(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    age = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    office_address = models.TextField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    total_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    profile_picture = models.URLField(null=True, blank=True)

    def __str__(self):
        return f"{self.fullname} (CEO)"


class Manager(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    age = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    team_size = models.IntegerField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    manager_level = models.CharField(max_length=50, null=True, blank=True)
    projects_handled = models.TextField(null=True, blank=True)
    profile_picture = models.URLField(null=True, blank=True)

    def __str__(self):
        return f"{self.fullname} (Manager)"
    
class Admin(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, null=True, blank=True)
    office_address = models.TextField(null=True, blank=True)
    profile_picture = models.URLField(null=True, blank=True)

    def _str_(self):
        return f"{self.fullname} (Admin)"


class Employee(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    designation = models.CharField(max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    reports_to = models.ForeignKey('Manager', on_delete=models.SET_NULL, to_field='email', null=True, blank=True)
    skills = models.TextField(null=True, blank=True)
    profile_picture = models.URLField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    marital_status = models.CharField(max_length=20, null=True, blank=True)
    nationality = models.CharField(max_length=50, null=True, blank=True)
    residential_address = models.TextField(null=True, blank=True)
    permanent_address = models.TextField(null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, null=True, blank=True)
    emergency_contact_no = models.CharField(max_length=20, null=True, blank=True)
    emp_id = models.CharField(max_length=50, unique=True, null=True)
    employment_type = models.CharField(max_length=50, null=True, blank=True)
    work_location = models.CharField(max_length=100, null=True, blank=True)
    team = models.CharField(max_length=100, null=True, blank=True)
    degree = models.CharField(max_length=100, null=True, blank=True)
    degree_passout_year = models.PositiveIntegerField(null=True, blank=True)
    institution = models.CharField(max_length=255, null=True, blank=True)
    grade = models.CharField(max_length=20, null=True, blank=True)
    languages = models.TextField(null=True, blank=True)
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
    ]

    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUP_CHOICES,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.fullname} (Employee)"

    def save(self, *args, **kwargs):
        try:
            this = Employee.objects.get(pk=self.pk)
            if this.profile_picture and this.profile_picture != self.profile_picture:
                if not str(this.profile_picture).startswith("http"):
                    this.profile_picture.delete(save=False)
        except Employee.DoesNotExist:
            pass
        super().save(*args, **kwargs)


# ------------------- DOCUMENTS & AWARDS -------------------
class Document(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', related_name='document')
    tenth = models.URLField(null=True, blank=True)
    twelth = models.URLField(null=True, blank=True)
    degree = models.URLField(null=True, blank=True)
    masters = models.URLField(null=True, blank=True)
    marks_card = models.URLField(null=True, blank=True)
    certificates = models.URLField(null=True, blank=True)
    award = models.URLField(null=True, blank=True)
    resume = models.URLField(null=True, blank=True)
    id_proof = models.URLField(null=True, blank=True)
    appointment_letter = models.URLField(null=True, blank=True)
    offer_letter = models.URLField(null=True, blank=True)
    releaving_letter = models.URLField(null=True, blank=True)
    resignation_letter = models.URLField(null=True, blank=True)
    achievement_crt = models.URLField(null=True, blank=True)
    bonafide_crt = models.URLField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Documents for {self.email.email}"


class Award(models.Model):
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email', related_name='awards')
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    photo = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.email}"


# ------------------- ATTENDANCE, LEAVE, PAYROLL -------------------
class Attendance(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email')
    fullname = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_verified = models.BooleanField(default=False)

    CHECK_IN_DEADLINE = time(10, 45)  # 10:45 AM

    def save(self, *args, **kwargs):
        # Fill fullname and department
        if self.email:
            try:
                employee = self.email.employee
                self.fullname = employee.fullname
                self.department = employee.department
            except Employee.DoesNotExist:
                pass

        # Check-in constraint
        if self.check_in:
            if self.check_in > self.CHECK_IN_DEADLINE:
                # Mark employee as absent
                AbsentEmployeeDetails.objects.get_or_create(
                    email=self.email,
                    date=self.date
                )
                # Prevent saving late check-in
                raise ValidationError(f"Check-in after {self.CHECK_IN_DEADLINE.strftime('%H:%M')} is not allowed.")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fullname or self.email} - {self.date}"

class Leave(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email')
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(max_length=50, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Pending')
    applied_on = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_on']

    def __str__(self):
        return f"{self.email.email} Leave from {self.start_date} to {self.end_date} [{self.status}]"


class Payroll(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email')
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pay_date = models.DateField(default=timezone.localdate)
    month = models.CharField(max_length=20)
    year = models.IntegerField(default=timezone.now().year)
    STD = models.IntegerField(default=0, help_text="Number of standard working days in the month")
    LOP = models.IntegerField(default=0, help_text="Loss of pay days (unpaid leave)")

    status = models.CharField(
        max_length=20,
        choices=[('Pending', 'Pending'), ('Paid', 'Paid'), ('Failed', 'Failed')],
        default='Pending'
    )

    class Meta:
        ordering = ['-pay_date']
        unique_together = ('email', 'month', 'year')

    def __str__(self):
        return f"Payroll for {self.email.email} - {self.month} {self.year}"


# ------------------- TASKS, REPORTS, PROJECTS, NOTICES, TICKETS -------------------
class TaskTable(models.Model):
    task_id = models.AutoField(primary_key=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email', related_name="tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks_assigned")
    priority = models.CharField(max_length=20, choices=[('Low','Low'),('Medium','Medium'),('High','High'),('Critical','Critical')], default='Medium')
    status = models.CharField(max_length=20, choices=[('Pending','Pending'),('In Progress','In Progress'),('Completed','Completed'),('On Hold','On Hold')], default='Pending')
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Task: {self.title} for {self.email.email} → {self.status}"


class Report(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports', null=True, blank=True, to_field='email')
    date = models.DateField(default=timezone.localdate)
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ('email', 'date')

    def __str__(self):
        return f"{self.title} ({self.date}) by {self.email.email if self.email else 'Unknown'}"


class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email', related_name='owned_projects')
    members = models.ManyToManyField(User, related_name='projects', blank=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('Planning','Planning'),('In Progress','In Progress'),('Completed','Completed'),('On Hold','On Hold')], default='Planning')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Notice(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    email = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, to_field='email', related_name='notices')
    posted_date = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    important = models.BooleanField(default=False)
    attachment = models.FileField(upload_to='notices/', null=True, blank=True)
    notice_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, to_field='email', related_name='notices_by')
    notice_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, to_field='email', related_name='notices_to')

    class Meta:
        ordering = ['-posted_date']

    def __str__(self):
        return self.title


class Ticket(models.Model):
    STATUS_CHOICES = [('Open','Open'),('In Progress','In Progress'),('Closed','Closed')]
    PRIORITY_CHOICES = [('Low','Low'),('Medium','Medium'),('High','High'),('Urgent','Urgent')]

    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_description = models.TextField(blank=True, null=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_assigned_by')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_assigned_to')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_closed_by')
    closed_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_closed_to')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} - {self.status}"


class EmployeeDetails(models.Model):
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email', related_name='employee_details')
    account_number = models.CharField(max_length=20, unique=True, null=True, blank=True)  # Added account_number
    father_name = models.CharField(max_length=100)
    father_contact = models.CharField(max_length=20)
    mother_name = models.CharField(max_length=100)
    mother_contact = models.CharField(max_length=20)
    wife_name = models.CharField(max_length=100)
    home_address = models.TextField()
    total_siblings = models.PositiveIntegerField()
    brothers = models.PositiveIntegerField()
    sisters = models.PositiveIntegerField()
    total_children = models.PositiveIntegerField()
    bank_name = models.CharField(max_length=100)
    branch = models.CharField(max_length=100)
    pf_no = models.CharField(max_length=50)
    pf_uan = models.CharField(max_length=50)
    ifsc = models.CharField(max_length=20)
    
    def __str__(self):
        return f"Employee Details of {self.email.email} ({self.account_number})"
    

class ReleavedEmployee(models.Model):
    email = models.EmailField(unique=True)  # stores plain email only
    fullname = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=50, blank=True, null=True)  # e.g. "employee", "hr", "admin"
    designation = models.CharField(max_length=100, blank=True, null=True)
    offboarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_releavedemployees'
        verbose_name = "Releaved Employee"
        verbose_name_plural = "Releaved Employees"

    def __str__(self):
        return self.email  # ✅ Only shows email (not with role)

class Holiday(models.Model):
    name = models.CharField(max_length=255)
    date = models.DateField()
    type = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="India")
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    weekday = models.CharField(max_length=10, blank=True)

    class Meta:
        unique_together = ('date', 'country')
        ordering = ['date']

    def save(self, *args, **kwargs):
        # Convert string to date if necessary
        if isinstance(self.date, str):
            self.date = datetime.strptime(self.date, '%Y-%m-%d').date()
        # Auto-set the weekday
        self.weekday = self.date.strftime('%A')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.date} - {self.weekday})"

class AbsentEmployeeDetails(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey('User', on_delete=models.CASCADE, to_field='email')
    fullname = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(default=timezone.localdate)

    def save(self, *args, **kwargs):
        # Automatically populate fullname and department from Employee
        if self.email:
            try:
                employee = self.email.employee  # Access related Employee
                self.fullname = employee.fullname
                self.department = employee.department
            except Exception:
                # Just in case Employee object doesn't exist
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fullname or self.email} - {self.date}"


class AppliedJobs(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    
    AVAILABILITY_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]
    
    email = models.EmailField(primary_key=True, db_column='email_id')  # Field name is 'email', DB column is 'email_id'
    fullname = models.CharField(max_length=255)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    phone_number = models.CharField(max_length=20)
    course = models.CharField(max_length=255, blank=True, null=True)
    resume = models.URLField(null=True, blank=True)
    available_for_training = models.CharField(max_length=3, choices=AVAILABILITY_CHOICES)
    work_experience = models.TextField(blank=True, null=True)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    hired = models.BooleanField(default=False)  # Boolean field, default not hired
    report = models.TextField(blank=True, null=True)  # Optional text field for report
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_appliedjobs'

    def __str__(self):
        return f"{self.full_name} ({self.email})"


class JobPosting(models.Model):
    JOB_TYPE_CHOICES = [
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Internship', 'Internship'),
        ('Contract', 'Contract'),
    ]

    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    department = models.CharField(max_length=255)
    description = models.TextField()    
    responsibilities = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    benefits = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)
    location = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default='Full-time')
    experience = models.CharField(max_length=50)
    salary = models.CharField(max_length=50, blank=True, null=True)
    apply_link = models.URLField(max_length=500, blank=True, null=True)
    posted_date = models.DateField()
    category = models.CharField(max_length=255)
    education = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_careers'

    def __str__(self):
        return f"{self.title} ({self.department})"
