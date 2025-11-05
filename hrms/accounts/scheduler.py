"""
Django APScheduler - Automatic Absent Marking Scheduler
Runs daily at 10:45 AM IST to mark employees as absent
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.utils import timezone
from datetime import time
import logging

from accounts.models import Employee, Attendance, AbsentEmployeeDetails, Holiday
from .constants import IST, CHECK_IN_DEADLINE

logger = logging.getLogger(__name__)


def mark_absent_employees():
    """
    Mark employees as absent if they haven't checked in by 10:45 AM IST.
    This runs automatically every day at 10:45 AM IST.
    Skips Sundays and holidays from Holiday table.
    """
    logger.info("="*60)
    logger.info("🕐 Starting automatic absent marking task...")
    
    try:
        now_ist = timezone.localtime(timezone.now(), IST)
        today = now_ist.date()
        current_time = now_ist.time()
        weekday_name = today.strftime('%A')
        
        logger.info(f"📅 Current IST time: {now_ist}")
        logger.info(f"📅 Date: {today} ({weekday_name})")
        
        # Check if today is Sunday
        if today.weekday() == 6:  # Sunday = 6
            logger.info("🎉 Today is Sunday - No absent marking needed!")
            logger.info("="*60)
            return
        
        # Check if today is a holiday
        holiday = Holiday.objects.filter(date=today).first()
        if holiday:
            logger.info(f"🎉 Today is a holiday: {holiday.name} - No absent marking needed!")
            logger.info("="*60)
            return
        
        # Check if current time is past 10:45 AM (CHECK_IN_DEADLINE)
        if now_ist.time() < CHECK_IN_DEADLINE:
            logger.warning(f"Too early ({now_ist.time()}). Skipping absent marking.")
            logger.warning(f"Too early ({current_time}). Skipping absent marking.")
            logger.info("="*60)
            return
        
        # Get all active employees
        all_employees = Employee.objects.all()
        marked_absent_count = 0
        skipped_already_absent = 0
        skipped_already_present = 0
        
        logger.info(f"👥 Total employees to check: {all_employees.count()}")
        logger.info("-"*60)
        
        for emp in all_employees:
            # Check if employee has checked in today
            has_checked_in = Attendance.objects.filter(
                email=emp.email,
                date=today,
                check_in__isnull=False
            ).exists()
            
            if not has_checked_in:
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
                        logger.info(f"  ❌ NEW ABSENT: {emp.fullname} ({emp.email.email})")
                else:
                    skipped_already_absent += 1
                    logger.info(f"  ⏩ SKIP (already absent): {emp.fullname} ({emp.email.email})")
            else:
                skipped_already_present += 1
        
        logger.info("-"*60)
        logger.info(f"✅ Task completed!")
        logger.info(f"   • Newly marked absent: {marked_absent_count}")
        logger.info(f"   • Already absent (skipped): {skipped_already_absent}")
        logger.info(f"   • Present (skipped): {skipped_already_present}")
        logger.info(f"   • Total: {all_employees.count()}")
        logger.info("="*60)
        
    except Exception as e:
        logger.error("="*60)
        logger.error(f"❌ Error in absent marking task: {str(e)}", exc_info=True)
        logger.error("="*60)


def start_scheduler():
    """
    Start the APScheduler background scheduler.
    This is called when Django starts.
    """
    scheduler = BackgroundScheduler(timezone=IST)
    
    # Schedule the task to run daily at 10:45 AM IST
    scheduler.add_job(
        mark_absent_employees,
        trigger=CronTrigger(hour=10, minute=45, timezone=IST),  # 10:45 AM IST daily
        id='mark_absent_daily',
        name='Mark Absent Employees Daily',
        replace_existing=True,
        max_instances=1,  # Prevent multiple instances running simultaneously
        coalesce=True,  # If multiple runs are queued, only run once
        misfire_grace_time=60  # Allow up to 60 seconds delay
    )
    
    logger.info("📅 Scheduler started! Absent marking will run daily at 10:45 AM IST")
    logger.info("   Configuration: max_instances=1, coalesce=True (prevents duplicates)")
    scheduler.start()
    
    return scheduler
