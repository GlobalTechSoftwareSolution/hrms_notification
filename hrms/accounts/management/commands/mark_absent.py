"""
Django management command to mark employees as absent if they haven't checked in by 10:45 AM IST.
This command should be scheduled to run daily at 10:45 AM IST using a cron job or task scheduler.

Usage:
    python manage.py mark_absent

Cron job example (Linux):
    45 10 * * * cd /path/to/project && python manage.py mark_absent

Windows Task Scheduler:
    Action: Start a program
    Program: python
    Arguments: manage.py mark_absent
    Trigger: Daily at 10:45 AM
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import time
import pytz
from accounts.models import Employee, Attendance, AbsentEmployeeDetails, Holiday

IST = pytz.timezone("Asia/Kolkata")


class Command(BaseCommand):
    help = 'Mark employees as absent if they have not checked in by 10:45 AM IST'

    def handle(self, *args, **options):
        now_ist = timezone.localtime(timezone.now(), IST)
        today = now_ist.date()
        current_time = now_ist.time()
        weekday_name = today.strftime('%A')
        
        self.stdout.write(f"Running absent marking task at {now_ist}")
        self.stdout.write(f"Date: {today} ({weekday_name})")
        
        # Check if today is Sunday
        if today.weekday() == 6:  # Sunday = 6
            self.stdout.write(
                self.style.WARNING(
                    f'🎉 Today is Sunday - No absent marking needed!'
                )
            )
            return
        
        # Check if today is a holiday
        is_holiday = Holiday.objects.filter(date=today).exists()
        if is_holiday:
            holiday = Holiday.objects.get(date=today)
            self.stdout.write(
                self.style.WARNING(
                    f'🎉 Today is a holiday: {holiday.name} - No absent marking needed!'
                )
            )
            return
        
        # Check if current time is past 10:45 AM (10:45)
        deadline = time(10, 45)  # 10:45 AM
        
        if current_time < deadline:
            self.stdout.write(
                self.style.WARNING(
                    f'Current time {current_time} is before deadline {deadline}. Skipping absent marking.'
                )
            )
            return
        
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
                    
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ❌ Marked absent: {emp.fullname} ({emp.email.email}) - {emp.department}'
                        )
                    )
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Successfully marked {marked_absent_count} employees as absent for {today}'
            )
        )
        self.stdout.write(f'  Total employees checked: {all_employees.count()}')
        self.stdout.write(f'  Present employees: {all_employees.count() - marked_absent_count}')
        
        if marked_absent_count == 0:
            self.stdout.write(self.style.SUCCESS('  🎉 All employees have checked in!'))
