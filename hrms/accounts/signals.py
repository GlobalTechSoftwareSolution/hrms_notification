# accounts/signals.py
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import User, HR, CEO, Manager, Admin, Employee, ReleavedEmployee, EmployeeDetails

# ------------------- CREATE OR UPDATE ROLE TABLES -------------------
@receiver(post_save, sender=User)
def manage_role_tables(sender, instance, created, **kwargs):
    """
    Whenever a User is created or updated:
    - Only create role records if user is approved (is_staff=True)
    - Delete old role records if role changes
    - Create EmployeeDetails for employees automatically
    """
    # Only process if user is staff (approved)
    if not instance.is_staff:
        return
    
    role = (instance.role or "").lower()
    
    # Delete records from other role tables to prevent duplicates
    role_tables = [HR, CEO, Manager, Admin, Employee]
    current_table = None
    
    if role == "employee":
        current_table = Employee
    elif role == "hr":
        current_table = HR
    elif role == "manager":
        current_table = Manager
    elif role == "admin":
        current_table = Admin
    elif role == "ceo":
        current_table = CEO
    
    # Delete from other role tables
    for table in role_tables:
        if table != current_table:
            try:
                obj = table.objects.get(email=instance)
                obj.delete()
            except table.DoesNotExist:
                pass
    
    # Create or get the correct role record
    if current_table:
        current_table.objects.get_or_create(email=instance)
        
        # Auto-create EmployeeDetails for employees
        if current_table == Employee:
            EmployeeDetails.objects.get_or_create(
                email=instance,
                defaults={
                    'father_name': '',
                    'father_contact': '',
                    'mother_name': '',
                    'mother_contact': '',
                    'wife_name': '',
                    'home_address': '',
                    'total_siblings': 0,
                    'brothers': 0,
                    'sisters': 0,
                    'total_children': 0,
                    'bank_name': '',
                    'branch': '',
                    'pf_no': '',
                    'pf_uan': '',
                    'ifsc': ''
                }
            )

# ------------------- BACKUP THEN CLEANUP ON USER DELETE -------------------
@receiver(pre_delete, sender=User)
def backup_and_cleanup_on_user_delete(sender, instance, **kwargs):
    """
    Before deleting a User:
    1) Ensure a ReleavedEmployee backup exists (create if missing).
    2) Remove related rows from role profile tables (HR/Manager/Admin/Employee/CEO).
    
    ReleavedEmployee stores email as a string field, so it's completely independent
    from the User table and will NEVER be affected by User deletions.
    """
    # 1) Ensure backup exists - check by email string, not FK
    email_str = instance.email
    
    if not ReleavedEmployee.objects.filter(email=email_str).exists():
        source_tables = [Employee, HR, Manager, Admin, CEO]
        for table in source_tables:
            try:
                obj = table.objects.get(email=instance)
                ReleavedEmployee.objects.create(
                    email=email_str,  # Store as string, not FK
                    fullname=getattr(obj, 'fullname', None),
                    phone=getattr(obj, 'phone', None),
                    role=getattr(instance, 'role', None),
                    department=getattr(obj, 'department', None),
                    designation=getattr(obj, 'designation', None),
                    date_of_birth=getattr(obj, 'date_of_birth', None),
                    date_joined=getattr(obj, 'date_joined', None),
                    profile_picture=getattr(obj, 'profile_picture', None),
                    skills=getattr(obj, 'skills', None),
                    # Copy additional employee fields
                    gender=getattr(obj, 'gender', None),
                    marital_status=getattr(obj, 'marital_status', None),
                    nationality=getattr(obj, 'nationality', None),
                    residential_address=getattr(obj, 'residential_address', None),
                    permanent_address=getattr(obj, 'permanent_address', None),
                    emergency_contact_name=getattr(obj, 'emergency_contact_name', None),
                    emergency_contact_relationship=getattr(obj, 'emergency_contact_relationship', None),
                    emergency_contact_no=getattr(obj, 'emergency_contact_no', None),
                    emp_id=getattr(obj, 'emp_id', None),
                    employment_type=getattr(obj, 'employment_type', None),
                    work_location=getattr(obj, 'work_location', None),
                    team=getattr(obj, 'team', None),
                    degree=getattr(obj, 'degree', None),
                    degree_passout_year=getattr(obj, 'degree_passout_year', None),
                    institution=getattr(obj, 'institution', None),
                    grade=getattr(obj, 'grade', None),
                    languages=getattr(obj, 'languages', None),
                    blood_group=getattr(obj, 'blood_group', None),
                )
                
                # Also copy EmployeeDetails if it exists
                try:
                    emp_details = EmployeeDetails.objects.get(email=instance)
                    # Update the ReleavedEmployee with family/bank details
                    releaved = ReleavedEmployee.objects.get(email=email_str)
                    releaved.account_number = emp_details.account_number
                    releaved.father_name = emp_details.father_name
                    releaved.father_contact = emp_details.father_contact
                    releaved.mother_name = emp_details.mother_name
                    releaved.mother_contact = emp_details.mother_contact
                    releaved.wife_name = emp_details.wife_name
                    releaved.home_address = emp_details.home_address
                    releaved.total_siblings = emp_details.total_siblings
                    releaved.brothers = emp_details.brothers
                    releaved.sisters = emp_details.sisters
                    releaved.total_children = emp_details.total_children
                    releaved.bank_name = emp_details.bank_name
                    releaved.branch = emp_details.branch
                    releaved.pf_no = emp_details.pf_no
                    releaved.pf_uan = emp_details.pf_uan
                    releaved.ifsc = emp_details.ifsc
                    releaved.save()
                except EmployeeDetails.DoesNotExist:
                    pass
                
                break
            except table.DoesNotExist:
                continue

    # 2) Clean up from role tables (ReleavedEmployee is not affected at all)
    role_tables = [Employee, HR, Manager, Admin, CEO]
    for table in role_tables:
        try:
            obj = table.objects.get(email=instance)
            obj.delete()
        except table.DoesNotExist:
            continue
