#!/usr/bin/env python3

# migrate.py - Migrar users.json a SQLite (open source, sin MongoDB)
# Comentarios en español. Ejecución: python migrate.py
import json, sqlite3, os, hashlib, secrets
from datetime import datetime

DB = "bot.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, nombre TEXT, grado TEXT, puesto TEXT, extension TEXT, password_hash TEXT, salt TEXT, rol TEXT DEFAULT 'externo', fecha_registro TEXT, ultimo_acceso TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT, archivo TEXT, categoria TEXT, responsable_email TEXT, responsable_nombre TEXT, fecha TEXT, contenido_preview TEXT, tokens_usados INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS ai_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, modelo_usado TEXT, tokens_prompt INTEGER DEFAULT 0, tokens_completion INTEGER DEFAULT 0, tokens_total INTEGER DEFAULT 0, costo_aproximado_dolares REAL DEFAULT 0.0, endpoint TEXT, user_email TEXT, pregunta_preview TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS feedback_screenshots (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, user_email TEXT, pregunta TEXT, respuesta TEXT, area_responsable TEXT, comentario TEXT, screenshot_path TEXT)")
    conn.commit(); conn.close()

def main():
    init_db()
    if not os.path.exists("users.json"):
        print("users.json no existe; creando base vacía.")
        return 0
    users = json.load(open("users.json", "r", encoding="utf-8"))
    count = 0
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    for email, info in users.items():
        try:
            c.execute("INSERT OR IGNORE INTO users (email, nombre, grado, puesto, extension, password_hash, salt, rol, fecha_registro, ultimo_acceso) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (email, info.get("nombre",""), info.get("grado",""), info.get("puesto",""), info.get("extension",""), info.get("hash",""), info.get("salt",""), info.get("rol","externo"), info.get("fecha_registro", datetime.now().isoformat()), info.get("fecha_registro", datetime.now().isoformat())))
            count += 1
        except Exception as e:
            print("Error migrando", email, e)
    conn.commit(); conn.close()
    print(f"Migración completa: {count} usuarios insertados en SQLite.")
    return 0

if __name__ == "__main__":
    exit(main())
