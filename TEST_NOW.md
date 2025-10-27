# 🧪 Test Automatic Absent Marking - 1:15 PM IST

## 🚀 Quick Test Steps

### Step 1: Install APScheduler
```bash
pip install apscheduler
```

### Step 2: Start Django Server
```bash
cd hrms
python manage.py runserver
```

### Step 3: Look for Success Message
You should see:
```
✅ Attendance scheduler initialized successfully
📅 Scheduler started! Absent marking will run daily at 1:15 PM IST
```

### Step 4: Wait for 1:15 PM IST
- **Current schedule**: Daily at **1:15 PM IST** (13:15)
- Watch your console/terminal

### Step 5: Check Console at 1:15 PM
You should see:
```
🕐 Starting automatic absent marking task...
Current IST time: 2025-01-27 13:15:00+05:30
  ❌ Marked absent: John Doe (john@example.com)
  ❌ Marked absent: Jane Smith (jane@example.com)
✓ Marked 2 employees as absent for 2025-01-27
  Total employees: 10
  Present: 8
```

---

## 🔍 What to Check

### ✅ **Success Indicators:**
1. Scheduler initialization message on server start
2. Console logs at exactly 1:15 PM IST
3. New records in `AbsentEmployeeDetails` table

### ❌ **If Nothing Happens:**

**Check 1: Is server running?**
```bash
# Server must be running at 1:15 PM
python manage.py runserver
```

**Check 2: Is APScheduler installed?**
```bash
pip list | grep apscheduler
# Should show: apscheduler 3.x.x
```

**Check 3: Check current IST time**
```python
# Run this in Django shell
python manage.py shell

from django.utils import timezone
import pytz
IST = pytz.timezone("Asia/Kolkata")
print(timezone.localtime(timezone.now(), IST))
```

---

## 📊 Verify Results

### Option 1: Check via API
```bash
GET http://localhost:8000/api/accounts/list_absent/
```

### Option 2: Django Shell
```python
python manage.py shell

from accounts.models import AbsentEmployeeDetails
from datetime import date

today_absent = AbsentEmployeeDetails.objects.filter(date=date.today())
print(f"Absent today: {today_absent.count()}")
for emp in today_absent:
    print(f"  - {emp.fullname} ({emp.email.email})")
```

### Option 3: Database Direct
```sql
SELECT * FROM accounts_absentemployeedetails 
WHERE date = CURRENT_DATE;
```

---

## 🎯 Expected Timeline

```
13:00 PM IST ─────────┐
                      │
13:10 PM IST ─────────┤  Waiting...
                      │
13:15 PM IST ─────────┤  🔔 TRIGGER FIRES!
                      │  Task executes automatically
                      │  Console shows logs
                      │  Database updated
13:20 PM IST ─────────┘  Task completed
```

---

## 💡 Tips

1. **Keep console visible** - You'll see real-time logs
2. **Don't refresh/restart** - Server must stay running
3. **Check system time** - Make sure your system clock is accurate
4. **First run** - If past 1:15 PM, it will run tomorrow at 1:15 PM

---

## 🐛 Troubleshooting

### Issue: "Module not found: apscheduler"
```bash
pip install apscheduler
# Then restart server
```

### Issue: No logs at 1:15 PM
- Check if server is running
- Check system time: `date` (Linux) or `time` (Windows)
- Check timezone: Should be IST

### Issue: Scheduler says "Too early"
- Wait until after 1:15 PM IST
- Or manually test: `python manage.py mark_absent`

---

## ✅ Success Checklist

- [ ] APScheduler installed (`pip install apscheduler`)
- [ ] Server started (`python manage.py runserver`)
- [ ] Initialization message shows "1:15 PM IST"
- [ ] Waiting for 1:15 PM IST
- [ ] Console shows task execution logs
- [ ] Database has new absent records

---

## 🎉 After Successful Test

Once verified, you can change back to 1:00 PM by editing:

**File**: `hrms/accounts/scheduler.py`  
**Line**: `CronTrigger(hour=13, minute=15, timezone=IST)`  
**Change to**: `CronTrigger(hour=13, minute=0, timezone=IST)`

Then restart server.

---

**Good luck with your test!** 🚀
