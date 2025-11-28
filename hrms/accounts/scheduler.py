"""
Background Scheduler for HRMS
Handles automated tasks like marking absent employees
"""
import logging
from datetime import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.utils import timezone
from django.conf import settings
from django.core.management import execute_from_command_line
import os
import sys

# Configure logger
logger = logging.getLogger(__name__)

# IST timezone (UTC+5:30)
IST = timezone.get_fixed_timezone(330)  # 5.5 hours = 330 minutes

def mark_absent_employees_daily():
    """
    Wrapper function to call the mark_absent_employees management command
    This is scheduled to run daily at 10:45 AM IST
    """
    try:
        # Execute the management command
        execute_from_command_line(['manage.py', 'mark_absent'])
        logger.info("Daily absent marking task executed successfully")
    except Exception as e:
        logger.error(f"Error executing daily absent marking task: {str(e)}")

def start_scheduler():
    """Start the APScheduler for automated tasks"""
    scheduler = BackgroundScheduler(timezone=IST)
    
    # Schedule the absent marking task for 10:45 AM IST daily
    scheduler.add_job(
        mark_absent_employees_daily,
        'cron',
        hour=10,
        minute=45,
        id='mark_absent_employees_daily',
        name='Mark Absent Employees Daily',
        max_instances=1,
        coalesce=True,
        replace_existing=True
    )
    
    scheduler.start()
    
    # Use plain text instead of emojis to avoid encoding issues
    logger.info("Calendar Scheduler started! Absent marking will run daily at 10:45 AM IST")
    logger.info("Configuration: max_instances=1, coalesce=True (prevents duplicates)")
