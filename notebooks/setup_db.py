import sqlite3
import os

os.makedirs('instance', exist_ok=True)
DB_PATH = 'instance/edupredict.db'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fullname TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    student_name TEXT NOT NULL,
    course TEXT NOT NULL,
    g1 REAL NOT NULL,
    g2 REAL NOT NULL,
    studytime REAL NOT NULL,
    absences REAL NOT NULL,
    failures REAL NOT NULL,
    prediction REAL NOT NULL,
    status TEXT NOT NULL,
    date TEXT NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES teachers (id)
)
''')

conn.commit()
conn.close()
print("✅ Tables created successfully in instance/edupredict.db")