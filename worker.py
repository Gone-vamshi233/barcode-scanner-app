from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from twilio.rest import Client
import os
import sqlite3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Twilio setup
twilio_client = Client(
    os.environ['TWILIO_ACCOUNT_SID'],
    os.environ['TWILIO_AUTH_TOKEN']
)
twilio_phone_number = os.environ['TWILIO_PHONE_NUMBER']
alert_phone_number = os.environ.get('ALERT_PHONE_NUMBER', '+919010741795')

# Worker function
def check_student_timeouts():
    now = datetime.now()
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    # Get all students who exited but not alerted yet
    c.execute("SELECT id, name, roll, exit_time FROM exit_logs WHERE alert_sent = 0")
    rows = c.fetchall()

    for row in rows:
        log_id, name, roll, exit_time_str = row
        exit_time = datetime.fromisoformat(exit_time_str)
        if now - exit_time > timedelta(minutes=2):
            try:
                twilio_client.messages.create(
                    body=f"🚨 {name} (Roll No: {roll}) did not return within 2 minutes.",
                    from_=twilio_phone_number,
                    to=alert_phone_number
                )
                print(f"✅ SMS sent to {alert_phone_number} for {roll}")
                c.execute("UPDATE exit_logs SET alert_sent = 1 WHERE id = ?", (log_id,))
                conn.commit()
            except Exception as e:
                print(f"❌ Error sending SMS for {roll}: {e}")

    conn.close()

# Scheduler setup
scheduler = BlockingScheduler()
scheduler.add_job(check_student_timeouts, 'interval', seconds=30)

if __name__ == '__main__':
    print("🔄 Starting SMS Worker...")
    scheduler.start()
