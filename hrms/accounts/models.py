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

    def _str_(self):
        return f"{self.email} ({self.role})"


class Department(models.Model):
    department_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    

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
    profile_picture = models.ImageField(upload_to='images/', null=True, blank=True)

    def _str_(self):
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
    profile_picture = models.ImageField(upload_to='images/', null=True, blank=True)

    def _str_(self):
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
    profile_picture = models.ImageField(upload_to='images/', null=True, blank=True)

    def _str_(self):
        return f"{self.fullname} (Manager)"


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
    current_address = models.TextField(null=True, blank=True)
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

    def __str__(self):
        return f"{self.fullname} (Employee)"

    def save(self, *args, **kwargs):
        # Only delete old file if it's a local file
        try:
            this = Employee.objects.get(pk=self.pk)
            if this.profile_picture and this.profile_picture != self.profile_picture:
                if not str(this.profile_picture).startswith("http"):
                    this.profile_picture.delete(save=False)
        except Employee.DoesNotExist:
            pass
        super(Employee, self).save(*args, **kwargs)


class Document(models.Model):
    email = models.ForeignKey(
        'User', on_delete=models.CASCADE, to_field='email', related_name='documents'
    )

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
        return f"Documents for {self.email}"


class Award(models.Model):
    email = models.ForeignKey(
        'User', on_delete=models.CASCADE, to_field='email', related_name='awards'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to='awards/photos/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def _str_(self):
        return f"{self.title} - {self.email}"



class Admin(models.Model):
    email = models.OneToOneField(User, on_delete=models.CASCADE, to_field='email', primary_key=True)
    fullname = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, null=True, blank=True)
    office_address = models.TextField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='images/', null=True, blank=True)

    def _str_(self):
        return f"{self.fullname} (Admin)"


class Attendance(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        to_field='email',
    )
    fullname = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_verified = models.BooleanField(default=False)  # True if within 100m radius

    def save(self, *args, **kwargs):
        if self.email:
            try:
                employee = self.email.employee  # assuming OneToOne relation
                self.fullname = employee.fullname
                self.department = employee.department
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fullname or self.email} - {self.date}"


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

    def _str_(self):
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

    def _str_(self):
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

    def _str_(self):
        return f"Task: {self.title} for {self.email.email} → {self.status}"


class Report(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    email = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports',
        null=True,
        blank=True,
        to_field='email'  # reference User.email as foreign key
    )
    date = models.DateField(default=timezone.localdate)
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "Daily Report"
        verbose_name_plural = "Daily Reports"
        unique_together = ('email', 'date')  # one report per user per date

    def _str_(self):
        return f"{self.title} ({self.date}) by {self.email.email if self.email else 'Unknown'}"
    

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

    def _str_(self):
        return self.name


class Notice(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    email = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        to_field='email', related_name='notices'
    )
    posted_date = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    important = models.BooleanField(default=False)
    attachment = models.FileField(upload_to='notices/', null=True, blank=True)
    notice_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        to_field='email', related_name='notices_by'
    )
    notice_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        to_field='email', related_name='notices_to'
    )

    class Meta:
        ordering = ['-posted_date']

    def __str__(self):
        return self.title
    
# class my_user(models.Model):
#     username = models.CharField(max_length=100)