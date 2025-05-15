from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv
from twilio.rest import Client
import sqlite3
import pandas as pd
import os

# Load environment variables
load_dotenv()

# Flask app
app = Flask(__name__)
app.secret_key = os.getenv('secret_key', 'default_secret_key')

@app.route('/test-env')
def test_env():
    twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
    return f'TWILIO_ACCOUNT_SID is: {twilio_sid}'

# Allowed logins
ALLOWED_EMAILS = {
    'gonevamshi43@gmail.com',
    'gonevamshi201@gmail.com',
    'kraju@cmrcet.ac.in',
    's.vaishnavi@cmrcet.ac.in'
}

# Flask-Login setup
login_manager = LoginManager(app)

# Twilio setup
twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = Client(twilio_account_sid, twilio_auth_token)

# In-memory barcode tracker
barcode_tracker = {}

# Database setup
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

init_db()

# User model
class User(UserMixin):
    def __init__(self, id, email, password):
        self.id = id
        self.email = email
        self.password = password

    @staticmethod
    def get(email):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        conn.close()
        if row:
            return User(*row)
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return User(*row)
    return None

@app.route('/')
def home():
    return render_template('home_page.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()

        if email not in ALLOWED_EMAILS:
            flash('You are not authorized to log in.')
            return render_template('login_page.html')

        user = User.get(email)
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('scanner'))
        flash('Invalid credentials.')
    return render_template('login_page.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        hashed_pw = generate_password_hash(password)

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_pw))
            conn.commit()
            flash("Signup successful. Please log in.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already exists.")
        finally:
            conn.close()
    return render_template('signup_page.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/scanner', methods=['GET', 'POST'])
@login_required
def scanner():
    student_name = ''
    roll_no = ''
    status = ''
    error = ''

    if request.method == 'POST':
        barcode = request.form['barcode'].strip()
        try:
            df = pd.read_excel('Book.xlsx', dtype=str)
            df.columns = df.columns.str.strip().str.lower()
            if {'barcode', 'name', 'rollno'}.issubset(df.columns):
                match = df[df['barcode'] == barcode]
                if not match.empty:
                    student_name = match.iloc[0]['name']
                    roll_no = match.iloc[0]['rollno']
                    now = datetime.now()

                    if barcode not in barcode_tracker:
                        barcode_tracker[barcode] = (student_name, roll_no, now, False)
                        status = "Exited record"
                    else:
                        exit_time, alert_sent = barcode_tracker[barcode][2], barcode_tracker[barcode][3]
                        if now - exit_time <= timedelta(minutes=2):
                            status = "Successfully returned"
                        else:
                            status = "Returned late"
                        del barcode_tracker[barcode]
                else:
                    error = "Barcode not found in Excel."
            else:
                error = "Missing columns: barcode, name, rollno"
        except FileNotFoundError:
            error = "Excel file 'Book.xlsx' not found."
        except Exception as e:
            error = f"Error: {str(e)}"

    return render_template('scanner_page.html', student_name=student_name, roll_no=roll_no, status=status, error=error)

@app.route('/support')
def support():
    return render_template('support_page.html')

# 🔁 SMS sending helper function
def send_sms_alert(name, roll):
    try:
        to_number = os.getenv('TO_PHONE_NUMBER')
        if not to_number:
            print("TO_PHONE_NUMBER environment variable not set.")
            return
        message = twilio_client.messages.create(
            body=f"ALERT:🚨 {name} (Roll No: {roll}) did not return within 2 minutes.",
            from_=twilio_phone_number,
            to=to_number,
        )
        print(f"SMS sent to {to_number} for {roll}: SID {message.sid}")
    except Exception as e:
        print(f"Error sending SMS for {roll}: {e}")

# ⏰ Background job
def check_student_timeouts():
    now = datetime.now()
    expired = []
    for barcode, (name, roll, exit_time, alert_sent) in barcode_tracker.items():
        if now - exit_time > timedelta(minutes=2) and not alert_sent:
            send_sms_alert(name, roll)
            barcode_tracker[barcode] = (name, roll, exit_time, True)
            expired.append(barcode)
    for barcode in expired:
        del barcode_tracker[barcode]
        # Scheduler setup (will be started later)
scheduler = BackgroundScheduler()
scheduler.add_job(check_student_timeouts, 'interval', seconds=30)
scheduler.start()
if __name__ == '__main__':
    app.run(debug=True)
