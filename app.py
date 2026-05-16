from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import os
import joblib
import pickle
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR, static_url_path='/static')
import secrets
app.secret_key = 'edupredict-esther-2026-fixed-key-12345'

DB_PATH = os.path.join(BASE_DIR, 'instance', 'edupredict.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
print("DATABASE PATH:", DB_PATH)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Load the ML model
try:
    model = joblib.load(os.path.join(BASE_DIR, 'models', 'student_model.pkl'))
    print(">>> MODEL LOADED SUCCESSFULLY")
except Exception as e:
    print(">>> MODEL LOAD FAILED:", e)
    model = None

def init_db():
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Drop old table so we can recreate with new columns
        cursor.execute('DROP TABLE IF EXISTS predictions')
        cursor.execute('DROP TABLE IF EXISTS teachers')
        
        cursor.execute('''
            CREATE TABLE teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                course TEXT NOT NULL,
                g1 REAL NOT NULL,
                g2 REAL NOT NULL,
                assignment REAL NOT NULL,
                attendance REAL NOT NULL,
                study_hours REAL NOT NULL,
                predicted_score REAL NOT NULL,
                risk_level TEXT NOT NULL,
                prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES teachers (id)
            )
        ''')
        conn.commit()
        conn.close()


@app.route('/')
def home():
    if 'teacher_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/index')
def index():
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            full_name = request.form['full_name']
            email = request.form['email']
            password = request.form['password']

            conn = get_db_connection()
            existing = conn.execute("SELECT * FROM teachers WHERE email =?", (email,)).fetchone()
            if existing:
                return render_template('register.html', error="Email already registered")

            conn.execute('INSERT INTO teachers (full_name, email, password) VALUES (?,?,?)',
                        (full_name, email, password))
            conn.commit()
            conn.close()

            flash("Registration successful! Please login.")
            return redirect(url_for('login'))
        except Exception as e:
            print(">>> Registration Error:", e)
            return render_template('register.html', error="Registration failed. Try again.")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        teacher = conn.execute("SELECT * FROM teachers WHERE email =? AND password =?", (email, password)).fetchone()
        conn.close()

        if teacher:
            session['teacher_id'] = teacher['id']
            session['teacher_name'] = teacher['full_name']
            return redirect(url_for('dashboard'))
        else:
                    return render_template('login.html', error="Invalid email or password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM predictions WHERE teacher_id =? ORDER BY id DESC", (session['teacher_id'],))
    predictions = cursor.fetchall()
    conn.close()
    total_students = len(predictions)
    at_risk_count = sum(1 for p in predictions if p['risk_level'] == "High Risk")
    return render_template('dashboard.html',
                          full_name=session.get('teacher_name'),
                          total_students=total_students,
                          at_risk_count=at_risk_count,
                          predictions=predictions)


import numpy as np

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            student_name = request.form['student_name']
            course = request.form['course']
            g1 = float(request.form['g1'])
            g2 = float(request.form['g2'])
            assignment = float(request.form['assignment'])
            attendance = float(request.form['attendance'])
            study_hours = float(request.form['study_hours'])
            
            # Formula calculation
            prediction_score = round((g2 * 0.4) + (g1 * 0.25) + (assignment / 10 * 0.15) + (attendance / 10 * 0.10) + (study_hours * 0.10 * 5), 1)
            prediction_score = min(prediction_score, 20.0)
            
            if prediction_score >= 16:
                risk_level = "Low Risk"
            elif prediction_score >= 12:
                risk_level = "Medium Risk"
            else:
                risk_level = "High Risk"
            
            conn = sqlite3.connect(DB_PATH)  # ← Changed this line
            conn.row_factory = sqlite3.Row
            conn.execute('''
                INSERT INTO predictions (teacher_id, student_name, course, g1, g2, assignment, attendance, study_hours, predicted_score, risk_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['teacher_id'], student_name, course, g1, g2, assignment, attendance, study_hours, prediction_score, risk_level))
            conn.commit()
            conn.close()
            
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(">>> PREDICT ERROR:", e)
            return f"Error in predict: {e}", 500
    
    return render_template('predict_form.html')

from flask import make_response
import io

@app.route('/download_letter/<int:id>')
def download_letter(id):
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    pred = conn.execute('SELECT * FROM predictions WHERE id = ? AND teacher_id = ?', 
                       (id, session['teacher_id'])).fetchone()
    conn.close()
    
    if not pred:
        return "Prediction not found", 404
    
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "EduPredict - Parent Notification Letter")
    p.setFont("Helvetica", 12)
    p.drawString(100, 710, f"Student: {pred['student_name']}")
    p.drawString(100, 690, f"Course: {pred['course']}")
    p.drawString(100, 670, f"Risk Level: {pred['risk_level']}")
    p.drawString(100, 650, f"Predicted Score: {pred['predicted_score']}/20")
    p.drawString(100, 610, "Dear Parent/Guardian,")
    p.drawString(100, 590, f"This letter is to inform you about {pred['student_name']}'s academic performance.")
    p.drawString(100, 570, f"Based on our EduPredict system, your child is currently at {pred['risk_level']}.")
    p.drawString(100, 550, "We recommend scheduling a meeting to discuss intervention strategies.")
    p.drawString(100, 510, "Sincerely,")
    p.drawString(100, 490, f"{session.get('full_name', 'Teacher')}")
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=letter_{pred["student_name"]}.pdf'
    return response


@app.route('/edit_prediction/<int:id>', methods=['GET', 'POST'])
def edit_prediction(id):
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        student_name = request.form['student_name']
        course = request.form['course']
        g1 = float(request.form['g1'])
        g2 = float(request.form['g2'])
        assignment = float(request.form['assignment'])
        attendance = float(request.form['attendance'])
        study_hours = float(request.form['study_hours'])
        
        # Recalculate with your formula
        prediction_score = round(
            (g2 * 0.4) + (g1 * 0.25) + (assignment / 10 * 0.15) + 
            (attendance / 10 * 0.10) + (study_hours * 0.10 * 5), 1
        )
        prediction_score = min(prediction_score, 20.0)
        
        if prediction_score >= 16:
            risk_level = "Low Risk"
        elif prediction_score >= 12:
            risk_level = "Medium Risk"
        else:
            risk_level = "High Risk"
        
        conn.execute('''
            UPDATE predictions SET 
            student_name=?, course=?, g1=?, g2=?, assignment=?, 
            attendance=?, study_hours=?, predicted_score=?, risk_level=?
            WHERE id=? AND teacher_id=?
        ''', (student_name, course, g1, g2, assignment, attendance, 
              study_hours, prediction_score, risk_level, id, session['teacher_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    
    # GET: Load existing data
    prediction = conn.execute(
        'SELECT * FROM predictions WHERE id = ? AND teacher_id = ?', 
        (id, session['teacher_id'])
    ).fetchone()
    conn.close()
    
    if prediction is None:
        return "Record not found", 404
        
    return render_template('edit_form.html', p=prediction)

@app.route('/delete_prediction/<int:id>')
def delete_prediction(id):
    if 'teacher_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM predictions WHERE id = ? AND teacher_id = ?', 
                 (id, session['teacher_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

from xhtml2pdf import pisa
from io import BytesIO
from flask import make_response
import pandas as pd

@app.route('/download_class_report') # ← this exact name
def download_class_report(): # ← this exact name
    if 'teacher_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    predictions = conn.execute('''
        SELECT student_name, course, g1, g2, assignment, attendance,
               study_hours, predicted_score, risk_level, prediction_date
        FROM predictions WHERE teacher_id =? ORDER BY student_name, course
    ''', (session['teacher_id'],)).fetchall()
    conn.close()

    df = pd.DataFrame(predictions, columns=predictions[0].keys() if predictions else [])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Class Report', index=False)

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=class_report.xlsx'
    return response
    return "Error generating PDF", 500
        
#with app.app_context():
 #   print(">>> CREATING TABLES")
  #  init_db()
   # print(">>> TABLES CREATED")

