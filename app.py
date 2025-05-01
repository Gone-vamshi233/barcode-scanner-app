from flask import Flask, render_template, redirect, url_for, request, flash, session
from datetime import datetime, timedelta
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = '1436'

ALLOWED_EMAILS = {'gonevamshi43@gmail.com', 'gonevamshi201@gmail.com'}

login_manager = LoginManager(app)
bcrypt = Bcrypt(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'gonevamshi201@gmail.com'
app.config['MAIL_PASSWORD'] = 'Gone vamshi123'
mail = Mail(app)

twilio_account_sid = 'AC3bd8c0b3854131e8bc650d5a02c18efd'
twilio_auth_token = '6873a5c06efeda99f63008882d7916d6'
twilio_phone_number = '+12098120571'
twilio_client = Client(twilio_account_sid, twilio_auth_token)

barcode_tracker = {}  # barcode: (student_name, roll_no, exit_time)

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
        user = c.fetchone()
        conn.close()
        if user:
            return User(user[0], user[1], user[2])
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1], user[2])
    return None

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if email not in ALLOWED_EMAILS:
            flash('You are not authorized to log in.')
            return render_template('login_page.html')

        user = User.get(email)
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('scanner'))
        flash('Invalid credentials')
    return render_template('login_page.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
            conn.commit()
            flash('Signup successful! Please log in.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists')
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
            normalized_columns = {col.strip().lower(): col for col in df.columns}

            required_cols = ['barcode', 'name', 'rollno']
            if all(col in normalized_columns for col in required_cols):
                barcode_col = normalized_columns['barcode']
                name_col = normalized_columns['name']
                rollno_col = normalized_columns['rollno']

                match = df[df[barcode_col] == barcode]
                if not match.empty:
                    student_name = match.iloc[0][name_col]
                    roll_no = match.iloc[0][rollno_col]
                    now = datetime.now()

                    if barcode not in barcode_tracker:
                        barcode_tracker[barcode] = (student_name, roll_no, now)
                        status = "Exited record"
                    else:
                        exit_time = barcode_tracker[barcode][2]
                        if now - exit_time <= timedelta(minutes=2):
                            status = "Entered record"
                        else:
                            status = "Returned late (SMS already sent if exceeded 2 mins)"
                        del barcode_tracker[barcode]

                else:
                    error = "Barcode not found in Excel."
            else:
                error = "Excel must have columns: Barcode, Name, and RollNo."
        except FileNotFoundError:
            error = "Excel file 'Book.xlsx' not found."
        except Exception as e:
            error = f"Error reading Excel: {str(e)}"

    return render_template(
        'scanner_page.html',
        student_name=student_name,
        roll_no=roll_no,
        status=status,
        error=error
    )

# Background job to check expired barcodes and send SMS
scheduler = BackgroundScheduler()

def check_student_timeouts():
    now = datetime.now()
    expired_barcodes = []
    for barcode, (student_name, roll_no, exit_time) in barcode_tracker.items():
        if now - exit_time > timedelta(minutes=2):
            twilio_client.messages.create(
                body=f"{student_name} (Roll No: {roll_no}) did not return within 2 minutes.",
                from_=twilio_phone_number,
                to='+919010741795'
            )
            expired_barcodes.append(barcode)
    for barcode in expired_barcodes:
        del barcode_tracker[barcode]

scheduler.add_job(check_student_timeouts, 'interval', seconds=30)
scheduler.start()

if __name__ == '__main__':
    app.run()
