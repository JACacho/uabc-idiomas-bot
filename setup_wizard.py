import os, sys, subprocess
from pathlib import Path

def preguntar(msg, default=""):
    resp = input(f"{msg}" + (f" [{default}]: " if default else ": ")).strip()
    return resp or default

print("=" * 50)
print("  Bienvenido al instalador de UABCBot")
print("=" * 50)
print()

nombre = preguntar("Nombre completo de la facultad")
siglas = preguntar("Siglas (ej. FIM, FCPS)")
url = preguntar("URL del sitio web oficial", "https://uabc.mx")
clave = preguntar("Clave de administrador")
gemini = preguntar("API key de Gemini (AIza...)")
gemini2 = preguntar("Segunda API key de Gemini (opcional)")
groq = preguntar("API key de Groq (gsk_...)")
openrouter = preguntar("API key de OpenRouter (sk-or-v1-...)")

env_content = f"""# Configuración generada automáticamente por setup_wizard.py
FACULTAD_NOMBRE={nombre}
FACULTAD_SIGLAS={siglas}
FACULTAD_URL={url}

GEMINI_API_KEY={gemini}
GEMINI_API_KEY_2={gemini2}
GROQ_API_KEY={groq}
OPENROUTER_API_KEY={openrouter}

CLAVE_ADMIN={clave}
PUERTO=7860
"""

Path(".env").write_text(env_content, encoding="utf-8")
print("\n✅ Archivo .env creado correctamente.")

# Crear directorio de datos si no existe
Path("datos_bot").mkdir(exist_ok=True)
Path("datos_scraper").mkdir(exist_ok=True)

print("\n📥 Ahora coloca tus documentos en la carpeta 'datos_bot/'")
print("   (o ejecuta 'python scraper_y_dedup.py' para extraer del sitio web).")
print()
respuesta = input("¿Ejecutar el scraping del sitio web ahora? [s/N]: ").strip().lower()
if respuesta == "s":
    print("\n🔍 Ejecutando scraper...")
    subprocess.run([sys.executable, "scraper_y_dedup.py"])

print("\n🗂️ Ahora indexando la información en la base vectorial...")
subprocess.run([sys.executable, "indexar_vectorial.py"])

print("\n" + "=" * 50)
print("  ✅ ¡Instalación completa!")
print(f"  Ejecuta 'start.bat' para arrancar el bot.")
print("=" * 50)