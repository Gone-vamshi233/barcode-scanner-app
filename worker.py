from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from twilio.rest import Client
import os
import sqlite3

# Load environment variables if needed
from dotenv import load_dotenv
load_dotenv()

# Twilio config from environment
twilio_client = Client(
    os.environ['TWILIO_ACCOUNT_SID'],
    os.environ['TWILIO_AUTH_TOKEN']
)
twilio_phone_number = os.environ['TWILIO_PHONE_NUMBER']
alert_phone_number = os.environ.get('ALERT_PHONE_NUMBER', '+919010741795')

# --- DATABASE BARCODE TRACKER ---
# If you're using a DB to store exit times, fetch data here.
# For this version, we simulate in-memory (should move to Redis or DB for production)

barcode_tracker = {
    # Example: 'ABC123': ('John Doe', '21IT123', datetime.now() - timedelta(minutes=3))
}

def check_student_timeouts():
    now = datetime.now()
    expired_barcodes = []

    for barcode, (student_name, roll_no, exit_time) in barcode_tracker.items():
        if now - exit_time > timedelta(minutes=2):
            twilio_client.messages.create(
                body=f"🚨 {student_name} (Roll No: {roll_no}) did not return within 2 minutes.",
                from_=twilio_phone_number,
                to=alert_phone_number
            )
            expired_barcodes.append(barcode)

    for barcode in expired_barcodes:
        del barcode_tracker[barcode]

scheduler = BlockingScheduler()
scheduler.add_job(check_student_timeouts, 'interval', seconds=30)

if __name__ == '__main__':
    print("🔄 Starting Scheduler...")
    scheduler.start()
