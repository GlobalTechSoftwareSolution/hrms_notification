from django.apps import AppConfig
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # Import and start scheduler only when Django is fully loaded
        from .scheduler import start_scheduler
        
        # Only start scheduler in the main process, not in subprocesses
        import os
        if os.environ.get('RUN_MAIN') == 'true':
            start_scheduler()
            # Use plain text instead of emojis to avoid encoding issues
            logger.info("Attendance scheduler initialized successfully")