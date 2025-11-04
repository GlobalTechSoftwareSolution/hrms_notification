import pytz
from datetime import time

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Attendance windows
CHECK_IN_START = time(7, 0)        # 07:00 AM IST
CHECK_IN_DEADLINE = time(10, 45)   # 10:45 AM IST
