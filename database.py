import sqlite3
import os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "uabc_bot.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        grado TEXT DEFAULT 'Lic.',
        puesto TEXT,
        extension TEXT,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        rol TEXT DEFAULT 'externo',
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ultimo_acceso TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archivo TEXT NOT NULL,
        categoria TEXT NOT NULL,
        responsable_email TEXT NOT NULL,
        responsable_nombre TEXT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        contenido_preview TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ai_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        modelo_usado TEXT NOT NULL,
        tokens_total INTEGER DEFAULT 0,
        costo_dolares REAL DEFAULT 0,
        endpoint TEXT,
        user_email TEXT
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos SQLite inicializada")

def create_user(email, nombre, password_hash, salt, grado="Lic.", puesto="", extension="", rol="externo"):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO users (email, nombre, password_hash, salt, grado, puesto, extension, rol) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (email, nombre, password_hash, salt, grado, puesto, extension, rol))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user(email):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_last_access(email):
    conn = get_db()
    conn.cursor().execute('UPDATE users SET ultimo_acceso = CURRENT_TIMESTAMP WHERE email = ?', (email,))
    conn.commit()
    conn.close()

def log_upload(archivo, categoria, email, nombre, preview=""):
    conn = get_db()
    conn.cursor().execute('''INSERT INTO uploads (archivo, categoria, responsable_email, responsable_nombre, contenido_preview) 
                             VALUES (?, ?, ?, ?, ?)''',
                          (archivo, categoria, email, nombre, preview))
    conn.commit()
    conn.close()

def log_ai_usage(modelo, tokens, costo, endpoint, email=""):
    conn = get_db()
    conn.cursor().execute('''INSERT INTO ai_usage (modelo_usado, tokens_total, costo_dolares, endpoint, user_email) 
                             VALUES (?, ?, ?, ?, ?)''',
                          (modelo, tokens, costo, endpoint, email))
    conn.commit()
    conn.close()

def get_usage_report():
    conn = get_db()
    c = conn.cursor()
    
    total = c.execute('''SELECT COUNT(*) as total, 
                                COALESCE(SUM(tokens_total), 0) as tokens, 
                                COALESCE(SUM(costo_dolares), 0) as costo 
                         FROM ai_usage''').fetchone()
    
    por_modelo = c.execute('''SELECT modelo_usado, COUNT(*) as count, 
                                     COALESCE(SUM(tokens_total), 0) as tokens 
                              FROM ai_usage 
                              GROUP BY modelo_usado''').fetchall()
    
    conn.close()
    return {
        'total': dict(total),
        'por_modelo': [dict(x) for x in por_modelo]
    }

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT email, nombre, grado, puesto, extension, rol, fecha_registro, ultimo_acceso FROM users')
    users = c.fetchall()
    conn.close()
    return [dict(u) for u in users]

# Inicializar al importar
init_db()