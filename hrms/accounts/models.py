from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone

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
    profile_picture = models.CharField(max_length=200, null=True, blank=True)

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
    profile_picture = models.CharField(max_length=200, null=True, blank=True)

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
    profile_picture = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.fullname} (Manager)"

class Employee(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    age = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    designation = models.CharField(max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    reports_to = models.ForeignKey(Manager, on_delete=models.SET_NULL, to_field='email', null=True, blank=True)
    skills = models.TextField(null=True, blank=True)
    profile_picture = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.fullname} (Employee)"

class Admin(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, null=True, blank=True)
    office_address = models.TextField(null=True, blank=True)
    profile_picture = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.fullname} (Admin)"

class Attendance(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        to_field='email',
    )
    date = models.DateField(default=timezone.localdate)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date']
        unique_together = ('email', 'date')

    def __str__(self):
        return f"{self.email.email} ({self.email.role}) - {self.date}"


class Leave(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email')
    department = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    leave_type = models.CharField(max_length=50, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Pending')
    applied_on = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_on']

    def __str__(self):
        return f"{self.email.email} - {self.department} Leave from {self.start_date} to {self.end_date} [{self.status}]"

class Payroll(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email')
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pay_date = models.DateField(default=timezone.localdate)
    month = models.CharField(max_length=20)
    year = models.IntegerField(default=timezone.now().year)
    status = models.CharField(max_length=20, choices=[
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Failed', 'Failed'),
    ], default='Pending')

    class Meta:
        ordering = ['-pay_date']
        unique_together = ('email', 'month', 'year')  # Keep unique per month/year per user

    def __str__(self):
        return f"Payroll for {self.email.email} - {self.month} {self.year}"

    def save(self, *args, **kwargs):
        self.net_salary = (self.basic_salary + self.allowances + self.bonus) - (self.deductions + self.tax)
        super().save(*args, **kwargs)

class TaskTable(models.Model):
    task_id = models.AutoField(primary_key=True)
    email = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        to_field='email',
        related_name="tasks"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_assigned"
    )
    department = models.CharField(max_length=100, null=True, blank=True)
    priority = models.CharField(
        max_length=20,
        choices=[
            ('Low', 'Low'),
            ('Medium', 'Medium'),
            ('High', 'High'),
            ('Critical', 'Critical'),
        ],
        default='Medium'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('Pending', 'Pending'),
            ('In Progress', 'In Progress'),
            ('Completed', 'Completed'),
            ('On Hold', 'On Hold'),
        ],
        default='Pending'
    )
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Task"
        verbose_name_plural = "Tasks"

    def __str__(self):
        return f"Task: {self.title} for {self.email.email} → {self.status}"

class Report(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    content = models.TextField(null=True, blank=True)  # For storing daily update details
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "Daily Report"
        verbose_name_plural = "Daily Reports"
        unique_together = ('created_by', 'date')  # One report per user per day

    def __str__(self):
        return f"{self.title} ({self.date}) by {self.created_by.email}"
    
class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    email = models.ForeignKey(User, on_delete=models.CASCADE, to_field='email', related_name='owned_projects')  # <-- renamed from owner to email
    members = models.ManyToManyField(User, related_name='projects', blank=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('Planning', 'Planning'),
            ('In Progress', 'In Progress'),
            ('Completed', 'Completed'),
            ('On Hold', 'On Hold'),
        ],
        default='Planning'
    )
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

    class Meta:
        ordering = ['-posted_date']

    def __str__(self):
        return self.title