import time
from app import scheduler

# Start the scheduler
scheduler.start()

print("✅ Worker scheduler started")

# Keep the process alive
while True:
    time.sleep(60)