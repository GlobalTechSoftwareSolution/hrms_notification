# Django APScheduler - Automatic Absent Marking Setup

## ✅ Installation Steps

### 1. Install APScheduler
```bash
pip install apscheduler
```

### 2. Update requirements.txt
Add this line to your requirements.txt:
```
apscheduler==3.10.4
```

### 3. Restart Django Server
```bash
# Stop current server (Ctrl+C)
# Then restart
python manage.py runserver
```

## 🎯 How It Works

When you start Django server (`python manage.py runserver`), the scheduler automatically:

1. **Starts** - Initializes APScheduler in background
2. **Schedules** - Sets up daily task at 1:00 PM IST
3. **Runs Automatically** - Executes `mark_absent_employees()` every day at 1 PM
4. **Logs** - Shows activity in console/logs

## 📊 Expected Output on Server Start

```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
January 27, 2025 - 10:30:15
Django version 5.2.6, using settings 'hrms.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.

✅ Attendance scheduler initialized successfully
📅 Scheduler started! Absent marking will run daily at 1:00 PM IST
```

## 🧪 Testing

### Test 1: Check if Scheduler is Running
Look for the success message in console when server starts.

### Test 2: Wait for 1:00 PM IST
Or manually trigger using management command:
```bash
python manage.py mark_absent
```

### Test 3: Check Logs
At 1:00 PM, you should see:
```
🕐 Starting automatic absent marking task...
Current IST time: 2025-01-27 13:00:00+05:30
  ❌ Marked absent: John Doe (john@example.com)
✓ Marked 1 employees as absent for 2025-01-27
```

## ⚙️ Configuration

The scheduler is configured in `accounts/scheduler.py`:

```python
scheduler.add_job(
    mark_absent_employees,
    trigger=CronTrigger(hour=13, minute=0, timezone=IST),  # 1:00 PM IST
    id='mark_absent_daily',
    name='Mark Absent Employees Daily',
    replace_existing=True,
)
```

To change the time, modify `hour=13, minute=0`.

## 🔍 Troubleshooting

### Issue: Scheduler doesn't start
**Solution**: Make sure you're running `python manage.py runserver`, not `manage.py migrate` or other commands.

### Issue: Task doesn't run at 1 PM
**Solution**: Check that your system clock is correct and server is running at that time.

### Issue: Multiple instances running
**Solution**: Restart the server. The `max_instances=1` setting prevents duplicates.

## 🚀 Production Deployment

For production (using Gunicorn/WSGI):

1. The scheduler will auto-start when server starts
2. Make sure only ONE server instance runs the scheduler
3. Alternative: Use Celery Beat for distributed systems

## ✅ Benefits of This Approach

- ✅ **Fully Automatic** - No external tools needed
- ✅ **Django Native** - Integrated with your Django app
- ✅ **No Cron Jobs** - Works on Windows/Linux/Mac
- ✅ **Easy to Monitor** - Logs in Django console
- ✅ **Starts with Server** - No separate service needed

Now your absent marking will work **automatically** as long as the Django server is running! 🎯
