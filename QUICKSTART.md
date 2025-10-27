# ⚡ Quick Start - Automatic Absent Marking

## 🚀 One-Time Setup (5 minutes)

### Step 1: Install Package
```bash
pip install apscheduler
```

### Step 2: Restart Server
```bash
python manage.py runserver
```

### Step 3: Verify
Look for this message in console:
```
✅ Attendance scheduler initialized successfully
📅 Scheduler started! Absent marking will run daily at 1:00 PM IST
```

## ✅ Done!

**That's it!** The system will now **automatically** mark employees as absent every day at 1:00 PM IST.

---

## 📊 What Happens Automatically

Every day at **1:00 PM IST**:
1. System checks all employees
2. If no check-in → Marks as absent in `AbsentEmployeeDetails` table
3. Logs the results

## 🧪 How to Test

### Option 1: Wait until 1:00 PM IST
Just let it run automatically!

### Option 2: Manual Test Anytime
```bash
python manage.py mark_absent
```

## 📍 Key Points

- ✅ **Works automatically** - No manual intervention needed
- ✅ **Starts with Django** - Runs when server starts
- ✅ **No external tools** - Pure Django/Python solution
- ✅ **Cross-platform** - Works on Windows, Linux, Mac

## ⚠️ Important

**Server must be running at 1:00 PM IST** for automatic execution. If server is down, the task won't run that day.

---

For detailed documentation, see `SCHEDULER_SETUP.md`
