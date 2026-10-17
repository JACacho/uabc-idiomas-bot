import os
from dotenv import load_dotenv
load_dotenv()
import re
import uuid
import json
import time
import base64
import asyncio
import hashlib
import secrets
import unicodedata
import tempfile
import requests
from datetime import datetime, date, timedelta
from collections import Counter
from google import genai as genai_lib
from google.genai import types as gtypes
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchAny

from database import log_upload, log_ai_usage, get_usage_report


scheduler = AsyncIOScheduler()



def generar_texto_directorio():
    try:
        with open(DIRECTORIO_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    lineas = ["=== DIRECTORIO DE ENCARGADOS - FACULTAD DE IDIOMAS UABC MEXICALI ===",
              "Para resolver trámites específicos, contacta directamente al encargado.", ""]
    for key, info in data.items():
        lineas.append(info.get("cargo", "").upper())
        lineas.append(f"Encargado: {info.get('nombre','')}")
        lineas.append(f"Correo: {info.get('correo','')}")
        ext = info.get('ext','')
        tel = info.get('telefono','')
        lineas.append(f"Teléfono: {tel}" + (f" ext. {ext}" if ext else ""))
        lineas.append(f"Atiende: {', '.join(info.get('temas', []))}")
        lineas.append("")
    return "\n".join(lineas)

def _tiene_fecha_pasada(texto):
    from datetime import date as _date
    hoy = _date.today()
    meses = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
             "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
    # Fechas tipo "18 de agosto" (asume año actual)
    # NO bloquear si es hoy, mañana o ayer (margen de 1 día)
    ayer = hoy - timedelta(days=1)
    for d, m in re.findall(r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)', texto.lower()):
        try:
            fecha_texto = _date(hoy.year, meses[m], int(d))
            if fecha_texto < ayer:
                return True
        except Exception:
            pass
    # Fechas tipo dd/mm/yyyy
    for d, m, y in re.findall(r'(\d{1,2})/(\d{1,2})/(\d{4})', texto):
        try:
            if _date(int(y), int(m), int(d)) < hoy:
                return True
        except Exception:
            pass
    return False

# ================= CONFIGURACIÓN =================
BASE = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_JSON = os.path.join(BASE, "directorio_encargados.json")
MANUAL = os.path.join(BASE, "Manual_Aspirantes_Idiomas_UABC.txt")
CARPETA = os.path.join(BASE, "datos_bot")
AUDIOS = os.path.join(BASE, "audios")
IMGS = os.path.join(BASE, "posters")
CAPTURAS = os.path.join(BASE, "capturas")
CONVS = os.path.join(BASE, "conversaciones")
FEEDBACK = os.path.join(BASE, "feedback")
CACHE = os.path.join(BASE, "cache.json")
USO = os.path.join(BASE, "uso.jsonl")
USERS = os.path.join(BASE, "users.json")
TOPFAQ_CACHE = os.path.join(BASE, "topfaq_cache.json")
QDRANT_URL = os.environ.get("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "").strip()
CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "")
CLAVE_DIRECCION = os.environ.get("CLAVE_DIRECCION", "")
CLAVE_FINANZAS = os.environ.get("CLAVE_FINANZAS", "")
CLAVE_SISTEMAS = os.environ.get("CLAVE_SISTEMAS", "")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPO", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_KEY_2 = os.environ.get("GEMINI_API_KEY_2", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_KEYS = [
    os.environ.get("OPENROUTER_API_KEY_11", ""),
    os.environ.get("OPENROUTER_API_KEY_2", ""),
    os.environ.get("OPENROUTER_API_KEY_3", ""),
    os.environ.get("OPENROUTER_API_KEY_4", ""),
    os.environ.get("OPENROUTER_API_KEY", ""),
]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k and k.startswith("sk-or-v1-")]

FACULTAD_NOMBRE = os.environ.get("FACULTAD_NOMBRE", "Facultad de Idiomas")
FACULTAD_SIGLAS = os.environ.get("FACULTAD_SIGLAS", "UABC")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
TOPFAQ_HOURS = float(os.environ.get("TOPFAQ_HOURS", "8"))
LOGO = os.path.join(BASE, "logo.png")
LOGO_URL = "https://raw.githubusercontent.com/JACacho/uabc-idiomas-bot/main/logo.png"
for d in (AUDIOS, CARPETA, CONVS, IMGS, FEEDBACK, CAPTURAS):
    os.makedirs(d, exist_ok=True)

CATS_INTERNAS = ("clases", "tareas", "internos")

def _mk_client(k):
    if not k:
        return None
    try:
        return genai_lib.Client(api_key=k)
    except Exception:
        return None

cliente_gemini = _mk_client(GEMINI_KEY)
cliente_gemini2 = _mk_client(GEMINI_KEY_2)

AREAS_RESP = {
    "Admisión": "admision.mxl@uabc.edu.mx",
    "CEC": "recepcionmxl@uabc.edu.mx",
    "Escolar/Escolaridad": "escolares_idiomas_mxl@uabc.edu.mx",
    "Egresados/Bolsa de trabajo": "egresados__idiomas__mxl@uabc.edu.mx",
    "Eventos": "idiomas.mxl@uabc.edu.mx",
    "Otro": "idiomas.mxl@uabc.edu.mx",
}

try:
    if not os.path.exists(LOGO):
        r = requests.get(LOGO_URL, timeout=10)
        if r.status_code == 200 and r.content:
            with open(LOGO, "wb") as f:
                f.write(r.content)
except Exception:
    pass

VOCES = {"es": "es-MX-DaliaNeural", "en": "en-US-AriaNeural", "fr": "fr-FR-DeniseNeural"}
DIAS = {0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves", 4: "viernes", 5: "sábado", 6: "domingo"}
MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
MESES_INV = {v: k for k, v in MESES.items()}
MESES_ALT = "(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
EXT_IMG = (".png", ".jpg", ".jpeg", ".webp")
PROMPT_POSTER = "Este es un anuncio o póster institucional. Extrae TODA la información útil (qué evento, quién invita, fecha, hora, lugar, contacto, requisitos) y devuélvela como texto claro en español, sin comentarios."
IMG_PRUEBA = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
# ============ TTS EN CASCADA (WaveNet → Edge → gTTS) ============
TTS_CREDENTIALS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", os.path.join(tempfile.gettempdir(), "tts_key.json"))
TTS_MONTHLY_LIMIT = int(os.environ.get("TTS_MONTHLY_LIMIT", "3500000"))
TTS_COUNTER_FILE = os.path.join(BASE, "tts_counter.json")

def _cargar_tts_counter():
    try:
        with open(TTS_COUNTER_FILE, encoding="utf-8") as f:
            d = json.load(f)
        mes_actual = datetime.now().strftime("%Y-%m")
        if d.get("mes") != mes_actual:
            return {"mes": mes_actual, "chars": 0}
        return d
    except Exception:
        return {"mes": datetime.now().strftime("%Y-%m"), "chars": 0}

def _guardar_tts_counter(d):
    try:
        with open(TTS_COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass

def _wavenet_disponible():
    c = _cargar_tts_counter()
    return c.get("chars", 0) < TTS_MONTHLY_LIMIT

def _setup_tts_credentials():
    """Si existe GOOGLE_CREDS_B64, escribe el JSON a disco al arrancar."""
    b64 = os.environ.get("GOOGLE_CREDS_B64", "")
    if b64 and not os.path.exists(TTS_CREDENTIALS_PATH):
        try:
            data = base64.b64decode(b64)
            with open(TTS_CREDENTIALS_PATH, "wb") as f:
                f.write(data)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = TTS_CREDENTIALS_PATH
            print(f"[TTS] Credenciales escritas en {TTS_CREDENTIALS_PATH}")
        except Exception as e:
            print(f"[TTS] Error escribiendo credenciales: {e}")
# ================================================================




MODELOS_OPENROUTER = []
MODELOS_GROQ = []
MODELOS_GEMINI = []
MODELOS_VISION_OR = []
async def actualizar_modelos():
    global MODELOS_OPENROUTER, MODELOS_GROQ, MODELOS_GEMINI
    async with httpx.AsyncClient() as client:
        # OpenRouter
        try:
            resp = await client.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {OR_KEY}"}, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                modelos = []
                vision_or = []
                for m in data.get("data", []):
                    pricing = m.get("pricing", {})
                    if pricing.get("prompt") == "0" and pricing.get("completion") == "0":
                        supported_params = m.get("supported_parameters", [])
                        if "tools" in supported_params:
                            modelos.append(m["id"])
                        # Detectar si acepta imágenes
                        mods = m.get("architecture", {}).get("input_modalities", [])
                        if "image" in mods:
                            vision_or.append(m["id"])
                MODELOS_OPENROUTER = modelos
                global MODELOS_VISION_OR
                MODELOS_VISION_OR = vision_or
            else:
                print(f"Error fetching OpenRouter models: {resp.status_code}")
        except Exception as e:
            print(f"Exception in OpenRouter model update: {e}")
        # Groq
        try:
            resp = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                modelos = [m["id"] for m in data.get("data", [])]
                MODELOS_GROQ = modelos
            else:
                print(f"Error fetching Groq models: {resp.status_code}")
        except Exception as e:
            print(f"Exception in Groq model update: {e}")
        # Gemini
        try:
            resp = await client.get(f"{GEMINI_URL}?key={GEMINI_KEY}", timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                modelos = []
                for m in data.get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        model_name = m["name"]
                        if model_name.startswith("models/"):
                            model_name = model_name[7:]
                        modelos.append(model_name)
                MODELOS_GEMINI = modelos
            else:
                print(f"Error fetching Gemini models: {resp.status_code}")
        except Exception as e:
            print(f"Exception in Gemini model update: {e}")


PALABRAS_EXCLUIDAS = ["whisper", "prompt-guard", "safeguard", "tts", "audio",
                      "image", "vision", "embed", "moderation", "guard",
                      "safety", "rerank", "transcribe", "codec", "lyria",
                      "imagen", "veo", "sora", "dall-e", "flux", "batch"]

def _es_candidato(nombre_modelo):
    n = nombre_modelo.lower()
    return not any(p in n for p in PALABRAS_EXCLUIDAS)

def validar_modelos_chat_sync():
    """Wrapper síncrono para correr en thread separado."""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        _asyncio.set_event_loop(loop)
        loop.run_until_complete(validar_modelos_chat())
    finally:
        loop.close()

async def validar_modelos_chat():
    global MODELOS_OPENROUTER, MODELOS_GROQ, MODELOS_GEMINI
    candidatos_or = [m for m in MODELOS_OPENROUTER if _es_candidato(m)][:8]
    candidatos_grq = [m for m in MODELOS_GROQ if _es_candidato(m)][:5]
    candidatos_gem = [m for m in MODELOS_GEMINI if _es_candidato(m)][:5]

    validos_or = []
    for m in candidatos_or:
        try:
            r = llamar_openai("Test", [], "Di solo: listo", OR_URL, OR_KEY, [m])
            if r and len(r) < 200:
                validos_or.append(m)
        except Exception:
            pass

    validos_grq = []
    for m in candidatos_grq:
        try:
            r = llamar_openai("Test", [], "Di solo: listo", GROQ_URL, GROQ_KEY, [m])
            if r and len(r) < 200:
                validos_grq.append(m)
        except Exception:
            pass

    validos_gem = []
    for m in candidatos_gem:
        try:
            r = llamar_gemini(GEMINI_KEY, "Test", [], "Di solo: listo", m)
            if r and len(r) < 200:
                validos_gem.append(m)
        except Exception:
            pass

    if validos_or: MODELOS_OPENROUTER = validos_or
    if validos_grq: MODELOS_GROQ = validos_grq
    if validos_gem: MODELOS_GEMINI = validos_gem
    print(f"OK Modelos validados: OR={len(validos_or)}, Groq={len(validos_grq)}, Gemini={len(validos_gem)}")
# ================= CEREBRO =================
def fecha_hoy_es():
    n = datetime.now()
    return f"{DIAS[n.weekday()]} {n.day} de {MESES[n.month]} de {n.year}"

def normalizar_texto(texto):
    """Convierte a minúsculas y elimina acentos/diéresis para comparación."""
    return ''.join(c for c in unicodedata.normalize('NFD', texto or '')
                   if unicodedata.category(c) != 'Mn').lower()
# ============ PRECIOS Y METADATA DE USO ============
PRECIOS_MODELOS = {
    "gemini-2.5-flash": {"entrada": 0.30, "salida": 2.50},
    "gemini-2.0-flash": {"entrada": 0.10, "salida": 0.40},
    "gemini-1.5-flash": {"entrada": 0.075, "salida": 0.30},
    "gemma": {"entrada": 0.05, "salida": 0.10},
    "llama-3.3-70b": {"entrada": 0.59, "salida": 0.79},
    "llama-3.1-8b": {"entrada": 0.05, "salida": 0.08},
    "llama-3.2": {"entrada": 0.05, "salida": 0.08},
    "qwen": {"entrada": 0.05, "salida": 0.10},
    "nemotron": {"entrada": 0.00, "salida": 0.00},
    "deepseek": {"entrada": 0.14, "salida": 0.28},
    "mistral": {"entrada": 0.10, "salida": 0.30},
    "default": {"entrada": 0.15, "salida": 0.60},
}

def _estimar_precio(modelo, tokens):
    """Estima costo USD. Modelos :free => $0."""
    if not modelo:
        return 0.0
    if ":free" in modelo.lower():
        return 0.0
    m = modelo.lower()
    for clave, precios in PRECIOS_MODELOS.items():
        if clave in m:
            promedio = (precios["entrada"] + precios["salida"]) / 2
            return (tokens / 1_000_000) * promedio
    d = PRECIOS_MODELOS["default"]
    return (tokens / 1_000_000) * ((d["entrada"] + d["salida"]) / 2)

def _detectar_area(texto):
    """Clasifica la pregunta por área para reportes."""
    t = normalizar_texto(texto)
    areas = [
        (("admision", "inscri", "ingresar", "ficha", "convocatoria", "nuevo ingreso"), "Admision"),
        (("cec", "curso", "horario", "ingles", "frances", "aleman", "italiano", "idioma"), "CEC"),
        (("escolar", "constancia", "kardex", "calificacion", "historial", "materia"), "Escolar"),
        (("egresado", "bolsa", "trabajo", "titulo", "titulacion", "servicio social", "practica"), "Egresados"),
        (("evento", "conferencia", "platica", "taller", "seminario", "congreso"), "Eventos"),
    ]
    for claves, area in areas:
        if any(k in t for k in claves):
            return area
    return "Otro"

_ultimo_uso = {}  # Metadata de la última respuesta
_T_START = time.time()  # Marca de tiempo para medir arranque
# =====================================================

def detectar_idioma(texto):
    t = normalizar_texto(texto)
    es_st = ["cuanto", "cuantos", "credito", "creditos", "titular", "titularme", "carrera", "tsu", "requisito", "admision", "horario", "cuesta", "precio", "donde", "como", "que", "para", "por", "con", "hola", "gracias", "necesito", "quiero", "informacion"]
    fr_st = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplom", "traduction", "salut", "credit", "je", "etud", "francais", "voud", "veux", "voaux", "quel", "quelle", "aime", "les", "des", "anglais", "alors", "carriere", "peux", "utilizar", "etudier", "trabajar", "quels", "quelles", "cest", "sont", "dans", "porque", "por qué", "comment"]
    en_st = ["hello", "thank", "how", "many", "degree", "translation", "what", "when", "where", "i", "would", "like", "to", "study", "french", "english", "do", "you", "for", "me", "is", "are", "the", "my", "can", "help"]

    # Cuenta coincidencias de palabra completa (con word boundary)
    def cuenta(palabras, texto_norm):
        return sum(1 for p in palabras if re.search(r'\b' + re.escape(p) + r'\b', texto_norm))

    h_es = cuenta(es_st, t)
    h_fr = cuenta(fr_st, t)
    h_en = cuenta(en_st, t)

    # Regla 1: Español gana si tiene 2+ señales claras
    if h_es >= 2:
        return "es"
    # Regla 2: Francés gana si tiene más señales que español
    if h_fr > h_es:
        return "fr"
    # Regla 3: Inglés gana si tiene 2+ señales y más que los otros
    if h_en >= 2 and h_en > h_es and h_en > h_fr:
        return "en"
    # Regla 4: Español gana si tiene 1 señal y no hay señales de otros idiomas
    if h_es >= 1 and h_fr == 0 and h_en == 0:
        return "es"
    # Regla 5: Francés si tiene al menos 1 señal
    if h_fr >= 1:
        return "fr"
    # Regla 6: Inglés si tiene 2+ señales
    if h_en >= 2:
        return "en"
    # Regla 7: Por defecto, español
    return "es"

def _fechas_doc(texto):
    fechas = []
    t = (texto or "").lower()
    for d, m, y in re.findall(r"(\d{1,2})\s+de\s+" + MESES_ALT + r"\s+de\s+(\d{4})", t):
        try:
            fechas.append(date(int(y), MESES_INV[m], int(d)))
        except Exception:
            pass
    for d, m in re.findall(r"(\d{1,2})\s+de\s+" + MESES_ALT, t):
        try:
            fechas.append(date(date.today().year, MESES_INV[m], int(d)))
        except Exception:
            pass
    for d, m, y in re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", t):
        try:
            fechas.append(date(int(y), int(m), int(d)))
        except Exception:
            pass
    return fechas

MEMORIA_OFICIAL = [
    (["credito", "titular", "credit"], {
        "es": "Para titularte en la Licenciatura en Traducción (LT) de la Facultad de Idiomas de la UABC necesitas un total de 349 créditos: 237 de materias obligatorias, 102 de materias optativas y 10 de prácticas profesionales. Para más detalles consulta idiomas.mxl.uabc.mx o llama al 686-689-0825.",
        "en": "To graduate from the Translation Bachelor's (LT) at the UABC Faculty of Languages you need 349 credits: 237 mandatory, 102 electives and 10 professional internships. Details at idiomas.mxl.uabc.mx or call 686-689-0825.",
        "fr": "Pour obtenir votre diplôme en Traduction (LT) à la Faculté de Langues de l'UABC, il faut 349 crédits : 237 obligatoires, 102 optionnels et 10 de stages. Détails sur idiomas.mxl.uabc.mx ou au 686-689-0825."}),
    (["carrera", "tsu", "tecnico", "técnico", "programas", "traduc", "translation", "traduction"], {
        "es": "La Facultad de Idiomas ofrece dos licenciaturas: Enseñanza de Lenguas (LEL) y Traducción (LT), además del Técnico Superior Universitario (TSU), una opción con enfoque práctico y rápida salida al campo laboral. Consulta la convocatoria vigente en idiomas.mxl.uabc.mx o llama al 686-689-0825.",
        "en": "The Faculty of Languages offers two bachelor's degrees: Language Teaching (LEL) and Translation (LT), plus a Higher University Technician (TSU) program with a practical focus and quick entry to the job market. To study Translation, check the current call at idiomas.mxl.uabc.mx or call 686-689-0825.",
        "fr": "La Faculté de Langues propose deux licences : Enseignement des Langues (LEL) et Traduction (LT), ainsi qu'un Technicien Supérieur Universitaire (TSU), option pratique avec insertion rapide sur le marché du travail. Pour étudier la traduction, consultez l'appel en cours sur idiomas.mxl.uabc.mx ou appelez le 686-689-0825."}),
    (["frances", "francés", "french", "français", "francais", "ingles", "inglés", "english", "anglais", "study", "estudiar", "etud", "curso", "cours", "cec", "horario"], {
        "es": "El Centro de Enseñanza de Lenguas (CEC) ofrece cursos de inglés, francés, alemán, italiano, portugués, ruso, chino mandarín, japonés, coreano y español para extranjeros, en formatos semanal, sabatino, intensivo e intersemestral, con horarios matutinos, vespertinos y nocturnos. Los grupos de cada periodo se publican en cecuabc.com. Informes: recepcionmxl@uabc.edu.mx o al 686 841-82-91 ext. 300.",
        "en": "The Language Teaching Center (CEC) offers courses in English, French, German, Italian, Portuguese, Russian, Mandarin, Japanese, Korean and Spanish for foreigners, in weekly, Saturday, intensive and inter-semester formats, morning, afternoon and evening. Groups are published each term at cecuabc.com. Info: recepcionmxl@uabc.edu.mx or 686 841-82-91 ext. 300.",
        "fr": "Le Centre d'Enseignement des Langues (CEC) propose des cours d'anglais, de français, d'allemand, d'italien, de portugais, de russe, de mandarin, de japonais, de coréen et d'espagnol pour étrangers, en formats hebdomadaire, samedi, intensif et intersemestriel, matin, après-midi et soir. Les groupes sont publiés chaque semestre sur cecuabc.com. Infos : recepcionmxl@uabc.edu.mx ou 686 841-82-91 poste 300."}),
    (["admision", "requisito", "admission"], {
        "es": "Para ingresar a la Facultad de Idiomas necesitas: 1) concluir el bachillerato con promedio aprobatorio, 2) certificado de bachillerato, acta de nacimiento y CURP, 3) registrarte en el portal de admisiones cuando abra la convocatoria (agosto y enero), y 4) presentar el Examen de Selección institucional. No se requiere inglés avanzado: la Facultad te forma desde cero. Fechas en admision.uabc.mx.",
        "en": "To enter the Faculty of Languages you need: 1) finish high school with a passing average, 2) high school certificate, birth certificate and CURP, 3) register on the admissions portal when the call opens (August and January), and 4) take the institutional Selection Exam. Advanced English is not required. Dates at admision.uabc.mx.",
        "fr": "Pour entrer à la Faculté de Langues : 1) terminer le lycée avec une moyenne suffisante, 2) certificat de lycée, acte de naissance et CURP, 3) s'inscrire sur le portail d'admission (août et janvier), et 4) passer l'Examen de Sélection. L'anglais avancé n'est pas requis. Dates sur admision.uabc.mx."}),
    (["que haces", "what do you do", "ayudar", "help", "sirves", "puedes hacer"], {
        "es": "Puedo informarte sobre créditos y planes de estudio, cursos y horarios del CEC, requisitos de admisión, carreras y TSU, y avisos o fechas oficiales de la Facultad de Idiomas de la UABC en Mexicali, en español, inglés o francés: te leo o te escucho. ¿Qué te gustaría saber?",
        "en": "I can help you with credits and study plans, CEC courses and schedules, admission requirements, degrees and TSU, and official notices and dates of the UABC Faculty of Languages in Mexicali, in Spanish, English or French: I read you or listen to you. What would you like to know?",
        "fr": "Je peux vous renseigner sur les crédits et plans d'études, les cours et horaires du CEC, les conditions d'admission, les licences et le TSU, ainsi que les avis et dates officielles de la Faculté de Langues de l'UABC à Mexicali, en espagnol, anglais ou français : je te lis ou je t'écoute. Que souhaitez-vous savoir ?"}),
]

def _limpiar_doc(texto):
    lineas = []
    for ln in (texto or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("===") or s.startswith("DOCUMENTO") or s.startswith("🖼️"):
            continue
        lineas.append(s)
    return "\n".join(lineas)

def _tokens(t):
    return set(re.findall(r"[a-záéíóúñü$0-9]+", (t or "").lower()))

def _es_valida(t):
    if not t:
        return False
    # Se eliminó la regla que rechazaba respuestas cortas con "?" 
    # porque bloqueaba saludos y preguntas de clarificación válidas.
    return True


def _es_interno_doc(fn):
    low = fn.lower()
    return any(f"_{c}" in low for c in CATS_INTERNAS)

def _cargar_docs(rol="externo"):
    docs = {}
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                if rol != "interno" and _es_interno_doc(fn):
                    continue
                try:
                    with open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore") as f:
                        docs[fn] = _limpiar_doc(f.read())
                except Exception:
                    continue
    return docs



_embedder = None
def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedder
def get_embedding(texto):
    return get_embedder().encode(texto).tolist()
_qdrant_adapter = None

class QdrantChromaAdapter:
    """Adaptador que imita la interfaz de ChromaDB usando Qdrant."""
    
    def __init__(self, client, collection_name="uabc_info"):
        self.client = client
        self.collection_name = collection_name
    
    def count(self):
        try:
            return self.client.count(collection_name=self.collection_name).count
        except Exception as e:
            print(f"[QdrantAdapter] Error count: {e}")
            return 0
    
    def _chroma_where_to_qdrant(self, where):
        if not where:
            return None
        conditions = []
        for key, value in where.items():
            if isinstance(value, dict) and "$in" in value:
                conditions.append(FieldCondition(key=key, match=MatchAny(any=list(value["$in"]))))
            elif isinstance(value, dict) and "$eq" in value:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value["$eq"])))
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        return Filter(must=conditions) if conditions else None
    
    def query(self, query_embeddings, n_results=8, where=None, include=None):
        vector = query_embeddings[0] if isinstance(query_embeddings, list) else query_embeddings
        qdrant_filter = self._chroma_where_to_qdrant(where)
        result = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=n_results,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        points = result.points if hasattr(result, "points") else result
        documents = [[p.payload.get("document", "") for p in points]]
        metadatas = [[{k: v for k, v in p.payload.items() if k != "document"} for p in points]]
        return {"documents": documents, "metadatas": metadatas}
    
    def add(self, embeddings, documents, metadatas, ids):
        import hashlib as _hashlib
        points = []
        for i in range(len(ids)):
            id_str = str(ids[i])
            id_int = int(_hashlib.md5(id_str.encode()).hexdigest()[:8], 16)
            payload = {"document": documents[i]}
            if metadatas[i]:
                payload.update(metadatas[i])
            vector = embeddings[i]
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            points.append(PointStruct(id=id_int, vector=vector, payload=payload))
        self.client.upsert(collection_name=self.collection_name, points=points)
    
    def get(self, include=None, limit=10000):
        result, _ = self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        documents = [r.payload.get("document", "") for r in result]
        metadatas = [{k: v for k, v in r.payload.items() if k != "document"} for r in result]
        return {"documents": documents, "metadatas": metadatas}


def get_chroma():
    global _qdrant_adapter
    if _qdrant_adapter is None:
        if not QDRANT_URL or not QDRANT_API_KEY:
            print("[QdrantAdapter] ADVERTENCIA: QDRANT_URL o QDRANT_API_KEY vacíos en .env")
        client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=60.0,
            check_compatibility=False,
            prefer_grpc=False,
        )
        _qdrant_adapter = QdrantChromaAdapter(client, "uabc_info")
    return _qdrant_adapter
def cargar_contexto(pregunta, rol="externo"):
    partes = []
    try:
        partes.append(generar_texto_directorio())
    except Exception as e:
        print(f"Error directorio: {e}")
    try:
        with open(MANUAL, encoding="utf-8", errors="ignore") as f:
            manual_text = _limpiar_doc(f.read())
            if manual_text:
                partes.append(manual_text)
    except Exception:
        pass
    try:
        vector = get_embedding(pregunta)
        if vector is None:
            return ""
        collection = get_chroma()
        if collection.count() > 0:
            where_filter = {"visibilidad": {"$in": ["publico", "interno"]}} if rol == "interno" else {"visibilidad": {"$in": ["publico"]}}
            results = collection.query(
                query_embeddings=[vector], n_results=8,
                where=where_filter, include=["documents"]
            )
            fragmentos = results.get("documents", [[]])[0]
            fragmentos = [f for f in fragmentos if not _tiene_fecha_pasada(f)]
            fragmentos = list(dict.fromkeys(fragmentos))  # Eliminar duplicados exactos
            # Si la pregunta menciona "hoy", "mañana" o "esta semana", añadir avisos recientes al inicio
            pregunta_lower = (pregunta or "").lower()
            if any(k in pregunta_lower for k in ["hoy", "mañana", "manana", "esta semana", "proxim"]):
                try:
                    todos = collection.get(include=["documents", "metadatas"])
                    recientes = []
                    for doc, meta in zip(todos.get("documents", []), todos.get("metadatas", [])):
                        archivo = meta.get("archivo", "")
                        if "20261006" in archivo or "20261007" in archivo:
                            recientes.append(doc)
                    if recientes:
                        fragmentos = recientes[:3] + fragmentos
                except Exception:
                    pass
            partes.extend(fragmentos)
    except Exception as e:
        print(f"Error vectorial: {e}")
    return "\n\n---\n\n".join(partes) if partes else ""

def respuesta_de_documentos(pregunta, rol="externo"):
    docs = _cargar_docs(rol)
    if not docs:
        return ""
    hoy = date.today()
    horizonte = hoy + timedelta(days=14)
    p = (pregunta or "").lower()
    if any(k in p for k in ("semana", "evento", "hoy", "mañana", "pronto", "avisos", "hay")):
        frescos = [t for t in docs.values() if any(hoy <= f <= horizonte for f in _fechas_doc(t))]
        frescos = list(dict.fromkeys(frescos))[:2]  # Eliminar duplicados antes de cortar a 2
        if frescos:
            return "📅 Según los avisos oficiales más recientes de la Facultad:\n\n" + "\n\n".join(t[:500] for t in frescos)
    qt = _tokens(pregunta)
    scored = sorted(((len(qt & _tokens(t)), t) for t in docs.values()), reverse=True)
    if scored and scored[0][0] >= 3:
        return "Según la información oficial de la Facultad: " + scored[0][1][:600]
    return ""

def sistema_prompt(contexto, rol="externo"):
    extra = ""
    if rol != "interno":
        extra = " El usuario es público general/aspirante: NO reveles información interna de clases, tareas o extensiones; si preguntan por ello, indica que esa información es para la comunidad UABC con cuenta institucional. "
    else:
        extra = " El usuario es de la comunidad UABC (@uabc.edu.mx): puedes incluir avisos internos de clases, tareas y extensiones. "
    return (
        f"Hoy es {fecha_hoy_es()}. Eres UABCBot {FACULTAD_SIGLAS}, asistente virtual de {FACULTAD_NOMBRE} de la UABC en Mexicali. "
        "Responde SIEMPRE en el idioma de la pregunta y en párrafos naturales, claros y concisos (máximo ~120 palabras salvo que pidan detalle). "
        "Si preguntan por COSTOS o PRECIOS, da la cifra exacta que aparezca en la INFORMACIÓN DISPONIBLE (monto, moneda y a quién aplica); si no aparece, indica consultar la convocatoria vigente en cecuabc.com o al 686 841-82-91 ext. 300. "
        "NUNCA repitas la pregunta del usuario ni respondas con otra pregunta; entrega siempre información concreta. "
        "FECHAS Y EVENTOS: si preguntan por 'hoy', 'mañana' o 'esta semana', SIEMPRE revisa si hay avisos que mencionen esas fechas específicas o un rango que las incluya. Si encuentras un aviso de suspensión o cambio de modalidad vigente para HOY o MAÑANA, DEBES informarlo claramente al usuario como PRIMERA respuesta. NUNCA digas 'no hay información' si existe un aviso vigente que cubra esas fechas. "
        "NUNCA menciones eventos, conferencias o talleres cuya fecha ya pasó. Si solo encuentras eventos pasados, indica que no hay eventos próximos por ahora. "
        "REGLAS DE ORO: responde ÚNICAMENTE a la pregunta del usuario; NUNCA reproduzcas el contexto como lista de preguntas y respuestas; "
        "NUNCA copies nombres de archivo, encabezados con ===, ni palabras como DOCUMENTO o CONTEXTO; reformula con tus palabras y usa solo datos disponibles. "
        "Si la información no aparece, sugiere contactar a la Facultad: tel. 686-689-0825, idiomas.mxl@uabc.edu.mx, idiomas.mxl.uabc.mx. "
        + extra +
        f"\nINFORMACIÓN DISPONIBLE:\n{contexto}"
    )

def llamar_gemini(api_key, sp, hist, pregunta, modelo):
    if not api_key:
        return None
    try:
        contents = []
        for m in hist:
            contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": pregunta}]})
        payload = {
            "system_instruction": {"parts": [{"text": sp}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.1}
        }
        url = f"{GEMINI_URL}/{modelo}:generateContent?key={api_key}"
        r = requests.post(url, json=payload, timeout=30)
        d = r.json()
        if "candidates" in d and len(d["candidates"]) > 0:
            t = d["candidates"][0]["content"]["parts"][0]["text"]
            if t.strip():
                _ultimo_uso["modelo"] = modelo
                _ultimo_uso["proveedor"] = "gemini"
                _ultimo_uso["exitoso"] = True
                return t.strip()
        return None
    except Exception as e:
        print(f"Error Gemini HTTP: {e}")
        return None

def llamar_openai(sp, hist, pregunta, url, key, modelos):
    if not key:
        return None
    for modelo in modelos:
        try:
            msgs = [{"role": "system", "content": sp}] + hist + [{"role": "user", "content": pregunta}]
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": modelo, "messages": msgs, "temperature": 0.1},
                timeout=15,
            )
            d = r.json()
            t = (d["choices"][0]["message"]["content"] or "").strip()
            if t:
                _ultimo_uso["modelo"] = modelo
                _ultimo_uso["proveedor"] = "openrouter" if "openrouter" in url else "groq"
                _ultimo_uso["exitoso"] = True
                return t
        except Exception:
            continue
    return None

def llamar_vision(url, key, modelos, b64, mime, prompt):
    if not key:
        return ""
    for modelo in modelos:
        try:
            msgs = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]}]
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": modelo, "messages": msgs, "temperature": 0.1},
                timeout=30,
            )
            d = r.json()
            t = (d["choices"][0]["message"]["content"] or "").strip()
            if t:
                return t
        except Exception:
            continue
    return ""

def _vision_gemini(api_key, data_b64, mime, prompt, modelo):
    if not api_key:
        return ""
    try:
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": data_b64}}
                ]
            }]
        }
        url = f"{GEMINI_URL}/{modelo}:generateContent?key={api_key}"
        r = requests.post(url, json=payload, timeout=60)
        d = r.json()
        if "candidates" in d and len(d["candidates"]) > 0:
            t = d["candidates"][0]["content"]["parts"][0]["text"]
            if t.strip():
                return t.strip()
    except Exception:
        pass
    return ""

def extraer_imagen(data, mime="image/jpeg"):
    errs = []
    b64_data = base64.b64encode(data).decode()

    # 1. Gemini Vision (Forzando modelos que soportan imágenes)
    modelos_vision = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for modelo in modelos_vision:
        t = _vision_gemini(GEMINI_KEY, b64_data, mime, PROMPT_POSTER, modelo)
        if t:
            _ultimo_uso["modelo"] = modelo
            _ultimo_uso["proveedor"] = "gemini_vision"
            _ultimo_uso["exitoso"] = True
            return t, ""
        errs.append(f"Gemini {modelo} fallo")

    # 2. Groq Vision
    t = llamar_vision(GROQ_URL, GROQ_KEY, ["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"], b64_data, mime, PROMPT_POSTER)
    if t:
        _ultimo_uso["modelo"] = "llama-3.2-90b-vision-preview"
        _ultimo_uso["proveedor"] = "groq_vision"
        _ultimo_uso["exitoso"] = True
        return t, ""
    errs.append("Groq visión no disponible")

    # 3. OpenRouter Vision Dinámico
    if MODELOS_VISION_OR:
        modelos_or = MODELOS_VISION_OR[:3] # Probamos hasta 3 modelos
        for modelo_or in modelos_or:
            t = llamar_vision(OR_URL, OR_KEY, [modelo_or], b64_data, mime, PROMPT_POSTER)
            if t:
                _ultimo_uso["modelo"] = modelo_or
                _ultimo_uso["proveedor"] = "openrouter_vision"
                _ultimo_uso["exitoso"] = True
                return t, ""
        errs.append("OpenRouter falló con todos los modelos")
    else:
        errs.append("No hay modelos de visión OpenRouter validados")

    return "", " | ".join(errs)

def probar_vision():
    out = {}
    b64_prueba = base64.b64encode(IMG_PRUEBA).decode()
    for i, key in enumerate((GEMINI_KEY, GEMINI_KEY_2), 1):
        out[f"gemini{i}"] = bool(_vision_gemini(key, b64_prueba, "image/png", "Describe la imagen en una palabra.", "gemini-2.5-flash"))
    b64 = base64.b64encode(IMG_PRUEBA).decode()
    out["groq"] = bool(llamar_vision(GROQ_URL, GROQ_KEY, ["llama-3.2-90b-vision-preview"], b64, "image/png", "Describe la imagen en una palabra."))
    out["openrouter"] = bool(llamar_vision(OR_URL, OR_KEY, ["meta-llama/llama-3.2-90b-vision-instruct:free"], b64, "image/png", "Describe la imagen en una palabra."))
    return out

def _cargar_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _guardar_cache(c):
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
    except Exception:
        pass

def _es_cacheable(texto):
    t = (texto or "").lower()
    return not (t.startswith("⚠️") or t.startswith("📅") or t.startswith("Según la información oficial") or len(t) < 60 or "ayudarte hoy" in t or "no está en el contexto" in t or "===" in t or "documento " in t or "manual de conocimiento" in t or len(t) > 900)

def responder(pregunta, historial, lang_pref="auto", rol="externo"):
    global _ultimo_uso
    _ultimo_uso = {"modelo": None, "proveedor": None, "exitoso": False, "fallback": False, "cache": False, "memoria": False}
    p = (pregunta or "").lower()
    p_sin = normalizar_texto(pregunta)   # sin acentos para comparaciones
    lang_detect = detectar_idioma(pregunta)
    lang = lang_pref if lang_pref in ("es", "en", "fr") else lang_detect
    cost_keywords = ("cuanto", "cuánto", "cuesta", "costo", "precio", "inscri")
    memory_keywords = ("credito", "titular", "carrera", "tsu")
    # NUEVO: Si preguntan por personas/contactos, saltar memoria y usar búsqueda vectorial
    persona_keywords = ("encargado", "encargada", "quien es", "quién es", "con quien", "con quién",
                        "contacto", "directorio", "correo de", "telefono de", "teléfono de",
                        "ing.", "lic.", "mtro.", "mtra.", "dr.", "dra.")
    es_costo = any(k in p_sin for k in cost_keywords)
    es_persona = any(k in p_sin for k in persona_keywords)

    if not es_persona:  # Solo usar memoria si NO es pregunta sobre personas
        if es_costo and not any(k in p_sin for k in memory_keywords):
            pass  # skip memory
        else:
            for claves, trad in MEMORIA_OFICIAL:
                if any(k in p_sin for k in claves):
                    if lang_pref not in ("es", "en", "fr"):
                        lang = lang_detect
                    _ultimo_uso["memoria"] = True
                    _ultimo_uso["exitoso"] = True
                    _ultimo_uso["modelo"] = "memoria_oficial"
                    _ultimo_uso["proveedor"] = "memoria"
                    return trad.get(lang, trad["es"]), lang
    clave = p.strip()[:120] + f"|{rol}"
    cache = _cargar_cache()
    if clave in cache:
        _ultimo_uso["cache"] = True
        _ultimo_uso["exitoso"] = True
        _ultimo_uso["modelo"] = "cache"
        _ultimo_uso["proveedor"] = "cache"
        return cache[clave][0], cache[clave][1]
    contexto = cargar_contexto(pregunta, rol)
    sp = sistema_prompt(contexto, rol)
    suf = {"es": " (Responde en español, conciso.)", "en": " (Answer in English, concise.)", "fr": " (Réponds en français, concis.)"}[lang]
    pregunta_final = pregunta + suf
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})    # Dynamic model selection with fallback per provider
    texto = None
    # 1. Gemini 1
    if not _es_valida(texto) and MODELOS_GEMINI and GEMINI_KEY:
        for modelo in MODELOS_GEMINI[:2]:
            texto = llamar_gemini(GEMINI_KEY, sp, hist, pregunta_final, modelo)
            if _es_valida(texto):
                break
    # 2. Gemini 2
    if not _es_valida(texto) and MODELOS_GEMINI and GEMINI_KEY_2:
        for modelo in MODELOS_GEMINI[:2]:
            texto = llamar_gemini(GEMINI_KEY_2, sp, hist, pregunta_final, modelo)
            if _es_valida(texto):
                break
    # 3. OpenRouter (rota por TODAS las keys)
    if not _es_valida(texto) and MODELOS_OPENROUTER:
        for key in OPENROUTER_KEYS:
            texto = llamar_openai(sp, hist, pregunta_final, OR_URL, key, MODELOS_OPENROUTER[:3])
            if _es_valida(texto):
                break
    # 4. Groq
    if not _es_valida(texto) and MODELOS_GROQ:
        groq_models = [m for m in MODELOS_GROQ if not any(x in m.lower() for x in ["whisper", "guard", "safeguard"])]
        if groq_models:
            texto = llamar_openai(sp, hist, pregunta_final, GROQ_URL, GROQ_KEY, groq_models)

    # Si aún no hay modelos validados (arranque en frío), avisar al usuario
    if not _es_valida(texto) and not MODELOS_GEMINI and not MODELOS_OPENROUTER and not MODELOS_GROQ:
        return "⏳ El sistema está iniciando y cargando los modelos de IA. Por favor, espera 1 o 2 minutos e intenta de nuevo.", lang
    # If still not valid, fallback to document response
    if not _es_valida(texto):
        fb = respuesta_de_documentos(pregunta, rol)
        if fb:
            _ultimo_uso["fallback"] = True
            _ultimo_uso["exitoso"] = True
            _ultimo_uso["modelo"] = "fallback_documentos"
            _ultimo_uso["proveedor"] = "fallback"
            return fb, lang
    if not _es_valida(texto):
        texto = "⚠️ Los motores de IA están saturados en este momento. Intenta de nuevo en unos segundos."
    texto = re.sub(r"^(\\s*\[[^\\]]{1,40}\\]\s*)+", "", texto).strip()
    if _es_cacheable(texto):
        cache[clave] = [texto, lang]
        _guardar_cache(cache)
    return texto, lang
def transcribir_groq(data):
    if not GROQ_KEY:
        return ""
    try:
        r = requests.post(
            GROQ_URL.replace("/chat/completions", "/audio/transcriptions"),
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("voz.webm", data, "audio/webm")},
            data={"model": "whisper-large-v3"},
            timeout=60,
        )
        return (r.json().get("text") or "").strip()
    except Exception:
        return ""

def transcribir(audio_bytes):
    # 1. Groq (especializado en audio)
    t = transcribir_groq(audio_bytes)
    if t:
        _ultimo_uso["modelo"] = "whisper-large-v3"
        _ultimo_uso["proveedor"] = "groq_audio"
        _ultimo_uso["exitoso"] = True
        return t, detectar_idioma(t)
        
    # 2. Gemini como respaldo (HTTP)
    b64_data = base64.b64encode(audio_bytes).decode()
    for api_key in (GEMINI_KEY, GEMINI_KEY_2):
        if not api_key:
            continue
        for mime in ("audio/webm", "audio/wav", "audio/mp3"):
            try:
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Transcribe textalmente este audio. Devuelve solo la transcripción."},
                            {"inline_data": {"mime_type": mime, "data": b64_data}}
                        ]
                    }]
                }
                modelo_gemini = "gemini-2.5-flash"
                url = f"{GEMINI_URL}/{modelo_gemini}:generateContent?key={api_key}"
                r = requests.post(url, json=payload, timeout=60)
                d = r.json()
                if "candidates" in d and len(d["candidates"]) > 0:
                    t = d["candidates"][0]["content"]["parts"][0]["text"]
                    if t.strip():
                        _ultimo_uso["modelo"] = modelo_gemini
                        _ultimo_uso["proveedor"] = "gemini_audio"
                        _ultimo_uso["exitoso"] = True
                        return t.strip(), detectar_idioma(t)
            except Exception:
                continue
    return "", "es"

def _limpiar_para_tts(texto):
    """Elimina markdown y símbolos que suenan mal en TTS."""
    t = texto or ""
    # Quitar bloques de código
    t = re.sub(r'```[\s\S]*?```', ' ', t)
    # Quitar código inline
    t = re.sub(r'`([^`]+)`', r'\1', t)
    # Quitar markdown de negritas, itálicas
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'__([^_]+)__', r'\1', t)
    t = re.sub(r'_([^_]+)_', r'\1', t)
    # Quitar headers markdown
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)
    # Quitar listas markdown (viñetas y números)
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.MULTILINE)
    t = re.sub(r'^\s*\d+\.\s+', '', t, flags=re.MULTILINE)
    # Quitar emojis
    t = re.sub(r'[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]', '', t)
    t = t.replace('⚠️', '').replace('⏳', '').replace('⌛', '').replace('🚩', '')
    # Quitar URLs
    t = re.sub(r'https?://\S+', ' ', t)
    # Quitar múltiples espacios/saltos
    t = re.sub(r'\s+', ' ', t).strip()
    return t

async def _tts_wavenet(texto_limpio, lang):
    """Nivel 1: Google Cloud TTS WaveNet. Retorna ruta o None."""
    try:
        from google.cloud import texttospeech
        from google.oauth2 import service_account
        if not os.path.exists(TTS_CREDENTIALS_PATH):
            return None
        creds = service_account.Credentials.from_service_account_file(TTS_CREDENTIALS_PATH)
        client = texttospeech.TextToSpeechClient(credentials=creds)
        voces = {
            "es": ("es-US", "es-US-Wavenet-A"),
            "en": ("en-US", "en-US-Wavenet-F"),
            "fr": ("fr-FR", "fr-FR-Wavenet-A"),
        }
        lang_code, voice_name = voces.get(lang, voces["es"])
        synthesis_input = texttospeech.SynthesisInput(text=texto_limpio)
        voice = texttospeech.VoiceSelectionParams(language_code=lang_code, name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        ruta = os.path.join(tempfile.gettempdir(), "respuesta_uabc.mp3")
        with open(ruta, "wb") as f:
            f.write(response.audio_content)
        c = _cargar_tts_counter()
        c["chars"] = c.get("chars", 0) + len(texto_limpio)
        _guardar_tts_counter(c)
        print(f"[TTS] WaveNet OK ({len(texto_limpio)} chars, total mes: {c['chars']})")
        return ruta
    except Exception as e:
        print(f"[TTS] WaveNet fallo: {e}")
        return None

async def _tts_edge(texto_limpio, lang):
    """Nivel 2: edge-tts (Microsoft). Retorna ruta o None."""
    try:
        import edge_tts
        voces = {
            "es": "es-MX-DaliaNeural",
            "en": "en-US-AriaNeural",
            "fr": "fr-FR-DeniseNeural",
        }
        voice = voces.get(lang, voces["es"])
        ruta = os.path.join(tempfile.gettempdir(), "respuesta_uabc.mp3")
        communicate = edge_tts.Communicate(texto_limpio, voice)
        await communicate.save(ruta)
        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            print(f"[TTS] Edge OK ({len(texto_limpio)} chars)")
            return ruta
        return None
    except Exception as e:
        print(f"[TTS] Edge fallo: {e}")
        return None

async def _tts_gtts(texto_limpio, lang):
    """Nivel 3: gTTS (Google Translate). Último recurso."""
    try:
        from gtts import gTTS
        idioma_gtts = {"es": "es", "en": "en", "fr": "fr"}.get(lang, "es")
        ruta = os.path.join(tempfile.gettempdir(), "respuesta_uabc.mp3")
        tts = gTTS(text=texto_limpio, lang=idioma_gtts, slow=False)
        tts.save(ruta)
        print(f"[TTS] gTTS OK ({len(texto_limpio)} chars)")
        return ruta
    except Exception as e:
        print(f"[TTS] gTTS fallo: {e}")
        return None

async def generar_voz(texto, lang):
    """Cascada: WaveNet → Edge → gTTS. Nunca falla (gTTS como último recurso)."""
    texto_limpio = _limpiar_para_tts(texto)
    if not texto_limpio:
        return None
    if _wavenet_disponible():
        ruta = await _tts_wavenet(texto_limpio, lang)
        if ruta:
            return ruta
    ruta = await _tts_edge(texto_limpio, lang)
    if ruta:
        return ruta
    return await _tts_gtts(texto_limpio, lang)

# ================= SERVICIOS =================
app = FastAPI()
@app.on_event("startup")
async def startup_event():
    global MODELOS_OPENROUTER, MODELOS_GROQ, MODELOS_GEMINI
    print(f"[startup] Iniciando en t={time.time()-_T_START:.2f} seg desde import")
    _setup_tts_credentials()
    # Tareas pesadas en paralelo para no bloquear el arranque
    async def _bootstrap_pesado():
        t0 = time.time()
        print(f"[startup] Bootstrap pesado iniciado en t={t0-_T_START:.2f} seg")
        try:
            print("[startup] Restaurando archivos desde GitHub (thread separado)...")
            await asyncio.to_thread(restaurar_desde_github)
            print(f"[startup] Restauracion completa en {time.time()-t0:.1f} seg")
        except Exception as e:
            print(f"[startup] Error restaurando: {e}")
        try:
            await actualizar_modelos()
            await asyncio.to_thread(validar_modelos_chat_sync)
            print(f"[startup] Modelos listos en {time.time()-t0:.1f} seg: OpenRouter={len(MODELOS_OPENROUTER)}, Groq={len(MODELOS_GROQ)}, Gemini={len(MODELOS_GEMINI)}")
            print(f"[startup] ✅ BOOTSTRAP TOTAL COMPLETO en {time.time()-_T_START:.1f} seg")
        except Exception as e:
            print(f"[startup] Error validando modelos: {e}")
    asyncio.create_task(_bootstrap_pesado())
    # Schedule daily update at 3:00 AM
    if not scheduler.running:
        scheduler.add_job(actualizar_modelos, 'cron', hour=3, minute=0)
        scheduler.add_job(validar_modelos_chat, 'cron', hour=3, minute=5)
        scheduler.add_job(respaldo_github_completo, 'cron', hour=3, minute=30)
        scheduler.start()
    # Background task for keep-alive
    async def keep_alive_task():
        port = int(os.environ.get("PORT", 7860))
        url = f"http://127.0.0.1:{port}/health"
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await client.get(url, timeout=10.0)
                except Exception as e:
                    print(f"Keep-alive request failed: {e}")
                await asyncio.sleep(600)
    asyncio.create_task(keep_alive_task())
    print(f"[startup] ⏱️ ARRANQUE VISIBLE en {time.time()-_T_START:.2f} seg (bot ya acepta queries)")
@app.get("/health")
async def health():
    return {"status": "ok"}


FAQ = [
    (["credito", "titular", "titul"], "¿Cuántos créditos necesito para titularme en Traducción?"),
    (["costo", "cuesta", "precio", "inscri"], "¿Cuánto cuesta inscribirme a las clases de inglés?"),
    (["horario", "cec"], "¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?"),
    (["admision", "requisito"], "¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?"),
    (["carrera", "tsu", "tecnico", "técnico"], "¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?"),
]

def _jload(p, d={}):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d

def _jdump(p, d):
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass

def _hash(clave, salt):
    return hashlib.sha256((salt + clave).encode("utf-8")).hexdigest()

def normalizar_faq(texto):
    t = (texto or "").lower()
    persona_keywords = ("encargado", "encargada", "quien es", "quién es", "con quien", "con quién",
                        "contacto", "directorio", "correo de", "telefono de", "teléfono de",
                        "ing.", "lic.", "mtro.", "mtra.", "dr.", "dra.")
    if any(k in t for k in persona_keywords):
        return texto or ""
    for claves, canonica in FAQ:
        if any(k in t for k in claves) and len(t) < 90:
            return canonica
    return texto or ""

def limpiar_tags(texto):
    return re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto or "").strip()

def github_subir(ruta_repo, contenido_bytes):
    if not GH_TOKEN or not GH_REPO:
        return "(sin respaldo GitHub)"
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=15)
        data = {"message": f"bot: actualiza {ruta_repo}", "content": base64.b64encode(contenido_bytes).decode()}
        if r.status_code == 200 and r.json().get("sha"):
            data["sha"] = r.json()["sha"]
        q = requests.put(url, json=data, headers=headers, timeout=25)
        return "☁️ Respaldo permanente en GitHub listo." if q.status_code in (200, 201) else "⚠️ No se pudo respaldar en GitHub."
    except Exception:
        return "⚠️ No se pudo respaldar en GitHub."
def github_listar_carpeta(ruta_repo):
    """Lista archivos en una carpeta del repo de GitHub. Regresa lista de nombres."""
    if not GH_TOKEN or not GH_REPO:
        return []
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        return [item["name"] for item in data if item.get("type") == "file"]
    except Exception as e:
        print(f"[github_listar_carpeta] Error {ruta_repo}: {e}")
        return []

def github_descargar(ruta_repo, ruta_local):
    """Descarga un archivo del repo de GitHub a disco local."""
    if not GH_TOKEN or not GH_REPO:
        return False
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return False
        data = r.json()
        if "content" not in data:
            return False
        contenido = base64.b64decode(data["content"])
        os.makedirs(os.path.dirname(ruta_local), exist_ok=True)
        with open(ruta_local, "wb") as f:
            f.write(contenido)
        return True
    except Exception as e:
        print(f"[github_descargar] Error {ruta_repo}: {e}")
        return False

def restaurar_desde_github():
    """Al arrancar, restaura archivos criticos desde GitHub."""
    print("[respaldo] Restaurando archivos desde GitHub...")
    archivos = ["uso.jsonl", "uabc_bot.db", "users.json", "cache.json", "topfaq_cache.json"]
    restaurados = 0
    for nombre in archivos:
        ruta_local = os.path.join(BASE, nombre)
        if github_descargar(nombre, ruta_local):
            print(f"[respaldo] OK Restaurado: {nombre}")
            restaurados += 1
        else:
            print(f"[respaldo] No encontrado en GitHub: {nombre}")
    for carpeta, prefijo in [(FEEDBACK, "feedback"), (CAPTURAS, "capturas"), (CONVS, "conversaciones"), (CARPETA, "datos_bot"), (IMGS, "posters"), (AUDIOS, "audios")]:
        try:
            nombres = github_listar_carpeta(prefijo)
            for nombre in nombres:
                ruta_local = os.path.join(carpeta, nombre)
                if github_descargar(f"{prefijo}/{nombre}", ruta_local):
                    restaurados += 1
        except Exception as e:
            print(f"[respaldo] Error restaurando {prefijo}: {e}")
    print(f"[respaldo] Restauracion completa: {restaurados} archivos")
    return restaurados

def respaldo_github_completo():
    """Sube a GitHub todos los archivos criticos de datos."""
    print("[respaldo] Subiendo archivos criticos a GitHub...")
    archivos = ["uso.jsonl", "uabc_bot.db", "users.json", "cache.json", "topfaq_cache.json"]
    subidos = 0
    for nombre in archivos:
        ruta_local = os.path.join(BASE, nombre)
        if os.path.exists(ruta_local):
            with open(ruta_local, "rb") as f:
                contenido = f.read()
            resultado = github_subir(nombre, contenido)
            if "listo" in resultado:
                subidos += 1
                print(f"[respaldo] OK Subido: {nombre} ({len(contenido)} bytes)")
            else:
                print(f"[respaldo] Fallo: {nombre}")
    carpetas = [
        (FEEDBACK, "feedback", (".txt",)),
        (CAPTURAS, "capturas", (".png",)),
        (CONVS, "conversaciones", (".json",)),
        (CARPETA, "datos_bot", (".txt",)),
        (IMGS, "posters", (".png", ".jpg", ".jpeg", ".webp")),
        (AUDIOS, "audios", (".mp3",)),
    ]
    for carpeta, prefijo, extensiones in carpetas:
        try:
            for fn in os.listdir(carpeta):
                if any(fn.lower().endswith(ext) for ext in extensiones):
                    ruta = os.path.join(carpeta, fn)
                    if os.path.isfile(ruta):
                        with open(ruta, "rb") as f:
                            github_subir(f"{prefijo}/{fn}", f.read())
        except Exception as e:
            print(f"[respaldo] Error {prefijo}: {e}")
    print(f"[respaldo] Completado. {subidos} archivos principales subidos.")
    return subidos

def crear_zip_respaldo():
    """Crea un ZIP con TODOS los datos y lo regresa como bytes."""
    import io
    import zipfile
    from datetime import datetime as _dt
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre in ["uso.jsonl", "uabc_bot.db", "users.json", "cache.json", "topfaq_cache.json", "directorio_encargados.json"]:
            ruta = os.path.join(BASE, nombre)
            if os.path.exists(ruta):
                zf.write(ruta, f"datos/{nombre}")
        for carpeta, prefijo in [(FEEDBACK, "feedback"), (CAPTURAS, "capturas"), (CONVS, "conversaciones"), (CARPETA, "datos_bot"), (IMGS, "posters"), (AUDIOS, "audios")]:
            try:
                for fn in os.listdir(carpeta):
                    ruta = os.path.join(carpeta, fn)
                    if os.path.isfile(ruta):
                        zf.write(ruta, f"{prefijo}/{fn}")
            except Exception:
                pass
        zf.writestr("INFO_RESPALDO.txt", f"Respaldo generado: {_dt.now().isoformat()}\nRepo: {GH_REPO}\n")
    return buffer.getvalue()

def github_borrar(ruta_repo):
    if not GH_TOKEN or not GH_REPO:
        return ""
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and r.json().get("sha"):
            requests.delete(url, json={"message": f"bot: borra {ruta_repo}", "sha": r.json()["sha"]}, headers=headers, timeout=25)
    except Exception:
        pass

def log_uso(texto, lang, via):
    try:
        area = _detectar_area(texto)
        modelo = _ultimo_uso.get("modelo") or "desconocido"
        proveedor = _ultimo_uso.get("proveedor") or "desconocido"
        exitoso = _ultimo_uso.get("exitoso", False)
        fallback = _ultimo_uso.get("fallback", False)
        fue_cache = _ultimo_uso.get("cache", False)
        fue_memoria = _ultimo_uso.get("memoria", False)
        tokens_estimados = max(1, len(texto) // 4)
        costo_estimado = _estimar_precio(modelo, tokens_estimados)
        with open(USO, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(),
                "texto": texto,
                "lang": lang,
                "via": via,
                "modelo": modelo,
                "proveedor": proveedor,
                "exitoso": exitoso,
                "fallback": fallback,
                "cache": fue_cache,
                "memoria": fue_memoria,
                "area": area,
                "tokens_estimados": tokens_estimados,
                "costo_estimado": costo_estimado,
            }, ensure_ascii=False) + "\n")
        try:
            log_ai_usage(modelo, tokens_estimados, costo_estimado, f"{via}:{area}", "")
        except Exception as e:
            print(f"Error log_ai_usage: {e}")
    except Exception as e:
        print(f"Error log_uso: {e}")

def leer_uso():
    try:
        with open(USO, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception:
        return []

def _indexar_archivo_robusto(ruta_archivo, visibilidad="publico"):
    """Indexa un solo archivo en ChromaDB. Tarda ~2 segundos."""
    try:
        from indexar_vectorial import chunk_text, extract_category
        with open(ruta_archivo, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        lines = [ln for ln in content.split('\n') if not ln.strip().startswith('===')]
        text = '\n'.join(lines).strip()
        if not text:
            return False
        chunks = chunk_text(text, target_len=500)
        if not chunks:
            return False
        embedder = get_embedder()
        embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()
        import os as _os, time as _time
        fname = _os.path.basename(ruta_archivo)
        category = extract_category(fname)
        ts = int(_time.time())
        ids = [f"{fname}_{i}_{ts}" for i in range(len(embeddings))]
        metadatas = [{"fuente": "maestro", "archivo": fname, "categoria": category, "visibilidad": visibilidad} for _ in embeddings]
        collection = get_chroma()
        collection.add(embeddings=embeddings, documents=chunks, metadatas=metadatas, ids=ids)
        print(f"✅ Indexado: {fname} ({len(chunks)} fragmentos)")
        return True
    except Exception as e:
        print(f"❌ Error indexado: {e}")
        return False





def guardar_aviso(texto, categoria="Avisos", visibilidad="publico", departamento="Otro",
                  responsable_nombre="", responsable_correo=""):
    depto_slug = re.sub(r'[^A-Za-z0-9]', '_', departamento)
    sufijo_vis = "_interno" if visibilidad == "interno" else ""
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + depto_slug + "_" + categoria + sufijo_vis + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: sin límite ===\n"
    contenido = cab + texto
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(contenido)
    try:
        log_upload(nuevo, categoria, responsable_correo or "anonimo@uabc.edu.mx",
                  responsable_nombre or "Encargado", texto[:200])
    except Exception as e:
        print(f"Error log_upload: {e}")
    return nuevo, github_subir(f"datos_bot/{nuevo}", contenido.encode("utf-8"))

def extraer_texto(ruta, nombre):
    if nombre.lower().endswith(".pdf"):
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        return "\n".join((p.extract_text() or "") for p in lector.pages)
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        return f.read()

def router(msg, hist, state, lang_pref, rol="externo"):
    state = state or {"pending": False, "active": False}
    texto = (msg or "").strip()
    if state.get("pending"):
        state["pending"] = False
        if texto == CLAVE_ADMIN:
            state["active"] = True
            return "✅ Acceso concedido, profe. Escribe tu aviso tal cual (o usa el panel ⚙️ para documentos, pósters y notas de voz; usa categoría Clases para info interna). Escribe SALIR para cerrar.", None, state
        return "❌ Clave incorrecta.", None, state
    if state.get("active"):
        if texto.upper() == "SALIR":
            state["active"] = False
            return "🔒 Sesión de administración cerrada. Vuelvo a modo aspirante.", None, state
        nuevo, resp = guardar_aviso(texto)
        return f"✅ Publicado y aprendido al instante. {resp}", None, state
    if "administraci" in texto.lower():
        state["pending"] = True
        return "🔐 Para entrar al modo de administración, escribe la clave de acceso.", None, state
    pregunta = normalizar_faq(texto)
    try:
        respuesta, lang = responder(pregunta, hist or [], lang_pref, rol)
    except Exception:
        respuesta, lang = responder(pregunta, [], lang_pref, rol)
    respuesta = limpiar_tags(respuesta)
    return respuesta, lang, state

async def producir_audio(respuesta, lang):
    try:
        ruta = await generar_voz(respuesta, lang or "es")
        if ruta and os.path.exists(ruta):
            nombre = str(uuid.uuid4()) + ".mp3"
            destino = os.path.join(AUDIOS, nombre)
            with open(ruta, "rb") as o, open(destino, "wb") as d:
                d.write(o.read())
            return "/audio/" + nombre
    except Exception:
        pass
    return None

@app.post("/api/register")
async def api_register(req: Request):
    d = await req.json()
    u = (d.get("usuario") or "").strip().lower()
    c = d.get("clave") or ""
    if len(u) < 3 or len(c) < 4:
        return {"ok": False, "error": "Usuario ≥ 3 y clave ≥ 4 caracteres."}
    users = _jload(USERS, {})
    if u in users:
        return {"ok": False, "error": "Ese usuario ya existe; inicia sesión."}
    salt = secrets.token_hex(8)
    rol = "interno" if u.endswith("@uabc.edu.mx") else "externo"
    users[u] = {"salt": salt, "hash": _hash(c, salt), "rol": rol}
    _jdump(USERS, users)
    return {"ok": True, "usuario": u, "rol": rol}

@app.post("/api/login")
async def api_login(req: Request):
    d = await req.json()
    u = (d.get("usuario") or "").strip().lower()
    c = d.get("clave") or ""
    users = _jload(USERS, {})
    rec = users.get(u)
    if not rec or rec["hash"] != _hash(c, rec["salt"]):
        return {"ok": False, "error": "Usuario o clave incorrectos."}
    return {"ok": True, "usuario": u, "rol": rec.get("rol", "externo")}

@app.post("/api/chat")
async def api_chat(req: Request):
    d = await req.json()
    st = d.get("state") or {}
    rol = d.get("rol", "externo")
    try:
        respuesta, lang, state = router(d.get("msg"), d.get("hist"), st, d.get("lang", "auto"), rol)
        audio = await producir_audio(respuesta, lang)
        if not (st.get("active") or st.get("pending")):
            log_uso(d.get("msg", ""), lang or d.get("lang", "auto"), "texto")
    except Exception as e:
        respuesta = f"⚠️ Error interno: {type(e).__name__}: {e}"
        audio = None
        state = st
        lang = "es"
    return {"reply": respuesta, "audio": audio, "state": state, "lang": lang}

@app.post("/api/voice")
async def api_voice(audio: UploadFile = File(...), hist: str = Form("[]"), state: str = Form("{}"), lang: str = Form("auto"), rol: str = Form("externo")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"texto": "", "reply": "⚠️ No logré escuchar bien. Intenta de nuevo más cerca del micrófono.", "audio": None, "state": state, "lang": "es"}
    st = json.loads(state)
    respuesta, lang2, state2 = router(texto, json.loads(hist), st, lang, rol)
    aud = await producir_audio(respuesta, lang2)
    if not (st.get("active") or st.get("pending")):
        log_uso(texto, lang2 or lang, "voz")
    return {"texto": texto, "reply": respuesta, "audio": aud, "state": state2, "lang": lang2}

@app.post("/api/voice_note")
async def voice_note(audio: UploadFile = File(...), categoria: str = Form("Avisos")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"estado": "⚠️ No logré escuchar la nota."}
    nuevo, resp = guardar_aviso(texto, categoria)
    import threading
    threading.Thread(target=_indexar_archivo_robusto, args=(os.path.join(CARPETA, nuevo),), daemon=True).start()
    return {"estado": f"✅ Nota de voz publicada: {nuevo}. {resp}"}

@app.post("/api/unlock")
async def api_unlock(req: Request):
    d = await req.json()
    return {"ok": d.get("clave") == CLAVE_ADMIN}

@app.post("/api/report")
async def report(req: Request):
    d = await req.json()
    if d.get("clave") != CLAVE_ADMIN:
        return {"error": "❌ Clave incorrecta"}
    lines = leer_uso()
    hoy = datetime.now().strftime("%Y-%m-%d")
    c = Counter(normalizar_faq(l["texto"]) for l in lines if l.get("texto"))
    idi = Counter(l.get("lang", "auto") for l in lines)
    return {
        "total": len(lines),
        "hoy": sum(1 for l in lines if l.get("ts", "").startswith(hoy)),
        "top": c.most_common(10),
        "idiomas": dict(idi),
    }

@app.get("/api/topfaq")
async def topfaq():
    now = time.time()
    try:
        with open(TOPFAQ_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if now - c.get("ts", 0) < TOPFAQ_HOURS * 3600:
            return c["items"]
    except Exception:
        pass
    cnt = Counter(normalizar_faq(l["texto"]) for l in leer_uso() if l.get("texto"))
    items = [{"q": q, "n": n} for q, n in cnt.most_common(8)]
    try:
        with open(TOPFAQ_CACHE, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "items": items}, f, ensure_ascii=False)
    except Exception:
        pass
    return items

@app.get("/api/tts")
async def api_tts(texto: str = "", lang: str = "es"):
    try:
        ruta = await generar_voz(texto, lang if lang in VOCES else "es")
        if ruta and os.path.exists(ruta):
            nombre = str(uuid.uuid4()) + ".mp3"
            destino = os.path.join(AUDIOS, nombre)
            with open(ruta, "rb") as o, open(destino, "wb") as d:
                d.write(o.read())
            return {"url": "/audio/" + nombre}
    except Exception:
        pass
    return {"url": ""}

@app.post("/api/feedback")
async def api_feedback(req: Request):
    d = await req.json()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    area = d.get("area", "Otro")
    captura_b64 = d.get("captura", "")
    captura_url = ""
    if captura_b64:
        try:
            header, data_b64 = captura_b64.split(",", 1) if "," in captura_b64 else ("", captura_b64)
            img_bytes = base64.b64decode(data_b64)
            img_name = ts + ".png"
            with open(os.path.join(CAPTURAS, img_name), "wb") as f:
                f.write(img_bytes)
            github_subir(f"capturas/{img_name}", img_bytes)
            captura_url = f"/captura/{img_name}"
        except Exception as e:
            captura_url = f"(error al guardar captura: {e})"
    contenido = (
        f"=== Feedback {ts} | Área: {area} | Reenviar a: {AREAS_RESP.get(area, AREAS_RESP['Otro'])} ===\n"
        f"CAPTURA: {captura_url or 'no disponible'}\n"
        f"PREGUNTA DEL USUARIO: {d.get('pregunta','')}\n"
        f"RESPUESTA DEL BOT: {d.get('respuesta','')}\n"
        f"COMENTARIO: {d.get('comentario','')}\n"
    )
    with open(os.path.join(FEEDBACK, ts + ".txt"), "w", encoding="utf-8") as f:
        f.write(contenido)
    github_subir(f"feedback/{ts}.txt", contenido.encode("utf-8"))
    return {"ok": True, "captura": captura_url}

@app.get("/captura/{nombre}")
async def captura(nombre: str):
    return FileResponse(os.path.join(CAPTURAS, nombre), media_type="image/png")

@app.get("/api/feedback/list")
async def api_feedback_list(clave: str = ""):
    if clave != CLAVE_ADMIN:
        return {"items": ["❌ Clave incorrecta"]}
    out = []
    for fn in sorted(os.listdir(FEEDBACK), reverse=True)[:10]:
        try:
            with open(os.path.join(FEEDBACK, fn), encoding="utf-8") as f:
                out.append(f.read())
        except Exception:
            pass
    return {"items": out or ["Sin feedbacks aún. 🎉"]}

@app.post("/api/upload")
async def api_upload(archivo: UploadFile = File(None), categoria: str = Form("Avisos"), vigencia: str = Form(""), reemplazar: str = Form("0"), texto_manual: str = Form(""), visibilidad: str = Form("publico"), departamento: str = Form("Otro"), responsable_nombre: str = Form(""), responsable_correo: str = Form("")):
    texto = texto_manual.strip()
    if archivo is not None:
        nombre_orig = archivo.filename or "doc.txt"
        ext = os.path.splitext(nombre_orig)[1].lower()
        data = await archivo.read()
    else:
        nombre_orig = "nota_manual.txt"
        ext = ".txt"
        data = b""
    if ext in EXT_IMG:
        mime = "image/png" if ext == ".png" else "image/jpeg"
        if not texto:
            texto, err_vis = extraer_imagen(data, mime)
        else:
            err_vis = ""
        if not texto:
            return {"estado": f"⚠️ Visión no disponible ahora ({err_vis}). Pega el texto del póster en el cuadro 📝 y pulsa Subir: se publica al instante."}
        iname = str(uuid.uuid4()) + ext
        with open(os.path.join(IMGS, iname), "wb") as f:
            f.write(data)
        texto = texto + f"\n🖼️ Póster original: /img/{iname}"
    elif data:
        tmp = os.path.join(BASE, "tmp_" + nombre_orig)
        with open(tmp, "wb") as f:
            f.write(data)
        texto = extraer_texto(tmp, nombre_orig) or texto
        os.remove(tmp)
    if not texto:
        return {"estado": "⚠️ Elige un archivo o pega el texto del aviso en el cuadro 📝."}
    if reemplazar == "1":
        for fn in list(os.listdir(CARPETA)):
            if fn.endswith(f"_{categoria}.txt"):
                os.remove(os.path.join(CARPETA, fn))
                github_borrar(f"datos_bot/{fn}")
    depto_slug = re.sub(r'[^A-Za-z0-9]', '_', departamento)
    sufijo_vis = "_interno" if visibilidad == "interno" else ""
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + depto_slug + "_" + categoria + sufijo_vis + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia or 'sin límite'} ===\n"
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(cab + texto)
    resp = github_subir(f"datos_bot/{nuevo}", (cab + texto).encode("utf-8"))
    import threading
    threading.Thread(target=_indexar_archivo_robusto, args=(os.path.join(CARPETA, nuevo),), daemon=True).start()
    return {"estado": f"✅ Guardado como {nuevo}. {resp}"}

@app.post("/api/delete")
async def api_delete(req: Request):
    d = await req.json()
    if d.get("clave") != CLAVE_ADMIN:
        return {"estado": "❌ Clave incorrecta"}
    nombre = (d.get("nombre") or "").strip()
    ruta = os.path.join(CARPETA, nombre)
    if os.path.exists(ruta):
        os.remove(ruta)
        github_borrar(f"datos_bot/{nombre}")
        return {"estado": f"🗑️ {nombre} eliminado (también del respaldo)."}
    return {"estado": "No encontrado."}

@app.get("/api/docs")
async def api_docs():
    archivos = [f for f in sorted(os.listdir(CARPETA)) if f.endswith(".txt")]
    return {"docs": archivos}

@app.get("/api/cache/clear")
async def cache_clear(clave: str = ""):
    if clave != CLAVE_ADMIN:
        return {"ok": False}
    try:
        os.remove(CACHE)
    except Exception:
        pass
    return {"ok": True}

@app.get("/api/debug")
async def api_debug():
    out = {"gemini": bool(cliente_gemini), "groq": bool(GROQ_KEY), "openrouter": bool(OR_KEY)}
    try:
        t, l = responder("Di solo la palabra: listo", [])
        out["respuesta"] = t[:100]
    except Exception as e:
        out["error_texto"] = f"{type(e).__name__}: {e}"
    return out

@app.get("/api/debug_vision")
async def api_debug_vision():
    return probar_vision()
@app.get("/api/modelos")
async def api_modelos():
    return {
        "openrouter": MODELOS_OPENROUTER,
        "groq": MODELOS_GROQ,
        "gemini": MODELOS_GEMINI
    }

@app.get("/api/test_ia")
async def api_test_ia():
    results = {}
    # Test OpenRouter
    if MODELOS_OPENROUTER:
        modelos_or = MODELOS_OPENROUTER if MODELOS_OPENROUTER else ["nvidia/nemotron-3-super-120b-a12b:free"]
        free_models = [m for m in modelos_or if m.endswith(":free") and any(word in m for word in ["coder", "nemotron", "qwen"])]
        if free_models:
            modelos_or = free_models
        test_model = modelos_or[0] if modelos_or else None
    else:
        test_model = None
    if test_model and OR_KEY:
        try:
            texto = llamar_openai("System: Test", [], "Di solo la palabra: listo", OR_URL, OR_KEY, [test_model])
            results["openrouter"] = {"modelo": test_model, "respuesta": texto[:100] if texto else None, "error": None}
        except Exception as e:
            results["openrouter"] = {"modelo": test_model, "respuesta": None, "error": str(e)}
    else:
        results["openrouter"] = {"modelo": test_model, "respuesta": None, "error": "No model or no API key"}

    # Test Groq
    groq_models = [m for m in MODELOS_GROQ if "whisper" not in m.lower()]
    if not groq_models:
        groq_models = ["llama-3.3-70b-versatile"]
    test_model_groq = groq_models[0]
    if test_model_groq and GROQ_KEY:
        try:
            texto = llamar_openai("System: Test", [], "Di solo la palabra: listo", GROQ_URL, GROQ_KEY, [test_model_groq])
            results["groq"] = {"modelo": test_model_groq, "respuesta": texto[:100] if texto else None, "error": None}
        except Exception as e:
            results["groq"] = {"modelo": test_model_groq, "respuesta": None, "error": str(e)}
    else:
        results["groq"] = {"modelo": test_model_groq, "respuesta": None, "error": "No model or no API key"}

    # Test Gemini
    if MODELOS_GEMINI:
        test_model_gemini = MODELOS_GEMINI[0]
    else:
        test_model_gemini = "gemini-3.8-flash"
    if test_model_gemini and GEMINI_KEY:
        try:
            texto = llamar_gemini(GEMINI_KEY, "System: Test", [], "Di solo la palabra: listo", test_model_gemini)
            results["gemini"] = {"modelo": test_model_gemini, "respuesta": texto[:100] if texto else None, "error": None}
        except Exception as e:
            results["gemini"] = {"modelo": test_model_gemini, "respuesta": None, "error": str(e)}
    else:
        results["gemini"] = {"modelo": test_model_gemini, "respuesta": None, "error": "No model or no API key"}

    return results


@app.post("/api/conv/save")
async def conv_save(req: Request):
    d = await req.json()
    cid = re.sub(r"[^a-zA-Z0-9_-]", "", d.get("id", ""))[:40] or "c"
    with open(os.path.join(CONVS, cid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": cid, "user": d.get("user", ""), "titulo": d.get("titulo", "Conversación"), "fecha": datetime.now().isoformat(), "msgs": d.get("msgs", [])}, f, ensure_ascii=False)
    return {"ok": True}

@app.get("/api/conv/list")
async def conv_list(user: str = ""):
    out = []
    for fn in os.listdir(CONVS):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(CONVS, fn), encoding="utf-8") as f:
                    d = json.load(f)
                if user and d.get("user") != user:
                    continue
                out.append({"id": d["id"], "titulo": d.get("titulo", "Conversación"), "fecha": d.get("fecha", "")})
            except Exception:
                pass
    out.sort(key=lambda x: x["fecha"], reverse=True)
    return out[:30]

@app.get("/api/conv/get")
async def conv_get(id: str = ""):
    cid = re.sub(r"[^a-zA-Z0-9_-]", "", id)[:40]
    p = os.path.join(CONVS, cid + ".json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.get("/audio/{nombre}")
async def audio(nombre: str):
    return FileResponse(os.path.join(AUDIOS, nombre), media_type="audio/mpeg")

@app.get("/img/{nombre}")
async def img(nombre: str):
    p = os.path.join(IMGS, nombre)
    mt = "image/png" if nombre.endswith(".png") else "image/jpeg"
    return FileResponse(p, media_type=mt)

@app.get("/logo.png")
async def logo():
    if os.path.exists(LOGO):
        return FileResponse(LOGO)
    return JSONResponse({})

PAGINA = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UABCBot {FACULTAD_SIGLAS} — {FACULTAD_NOMBRE} de la UABC en Mexicali</title>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: #eef1f4; }
  #toast { display: none; position: fixed; top: 12px; left: 50%; transform: translateX(-50%); color: #fff; padding: 13px 22px; border-radius: 14px; font-size: 14.5px; z-index: 99; box-shadow: 0 4px 16px rgba(0,0,0,.35); max-width: 92%; text-align: center; }
  .wrap { max-width: 100%; margin: 0 auto; height: 100vh; display: flex; flex-direction: row; }
  #side { width: 260px; background: #004d38; color: #fff; padding: 14px 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
  #side b { font-size: 14px; }
  #side button { background: rgba(255,255,255,.12); color: #fff; border: none; border-radius: 10px; padding: 9px 10px; text-align: left; cursor: pointer; font-size: 12.5px; }
  #side button:hover { background: rgba(255,255,255,.25); }
  main { flex: 1; display: flex; flex-direction: column; height: 100vh; }
  header { background: linear-gradient(135deg, #00684a, #00855f); color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 10px; border-radius: 0 0 18px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.15); flex-wrap: wrap; }
  header img { width: 54px; height: 54px; background: #fff; border-radius: 12px; padding: 3px; }
  header h1 { font-size: 17px; } header p { font-size: 12px; opacity: .85; }
  .langs { display: flex; gap: 5px; margin-left: 10px; }
  .langs button { font-size: 11px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: transparent; color: #fff; cursor: pointer; }
  .langs button.on { background: #f7941d; border-color: #f7941d; font-weight: 700; }
  .hbtn { background: rgba(255,255,255,.15); border: none; border-radius: 999px; width: 36px; height: 36px; cursor: pointer; font-size: 16px; }
  #user { background: #8fe3b0; }
  #nuevo { margin-left: auto; }
  #chat { flex: 1; overflow-y: auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 82%; display: flex; flex-direction: column; gap: 4px; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.bot { align-self: flex-start; align-items: flex-start; }
  .bub { padding: 10px 14px; border-radius: 16px; font-size: calc(14.5px * var(--fs, 1)); line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,.12); white-space: pre-wrap; }
  .user .bub { background: #d9f6c8; border-bottom-right-radius: 4px; }
  .bot .bub { background: #fff; border-bottom-left-radius: 4px; }
  .msg audio { width: 260px; max-width: 100%; }
  .think .bub { background: #fff; color: #666; font-style: italic; }
  .dots::after { content: ''; animation: pts 1.2s steps(4) infinite; }
  @keyframes pts { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75% { content: '...'; } }
  .opts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .opts button { font-size: calc(12.5px * var(--fs, 1)); padding: 7px 11px; border-radius: 999px; border: 1px solid #00855f; background: #f2fbf6; color: #00684a; cursor: pointer; }
  .opts button:hover { background: #00855f; color: #fff; }
  .nota { display: block; margin-top: 9px; font-size: calc(12px * var(--fs, 1)); color: #888; }
  .bar { display: flex; gap: 8px; padding: 10px 12px 14px; align-items: center; }
  #mic { width: 46px; height: 46px; border-radius: 50%; border: none; background: #00684a; color: #fff; font-size: 19px; cursor: pointer; flex-shrink: 0; }
  #mic.rec { background: #d32f2f; animation: pulso 1s infinite; }
  @keyframes pulso { 50% { transform: scale(1.12); } }
  #inp { flex: 1; border: 1px solid #cfd8dc; border-radius: 999px; padding: 12px 18px; font-size: calc(15px * var(--fs, 1)); outline: none; }
  #inp:focus { border-color: #00855f; }
  #send { width: 46px; height: 46px; border-radius: 50%; border: none; background: #f7941d; color: #fff; font-size: 18px; cursor: pointer; flex-shrink: 0; }
  #fb { width: 46px; height: 46px; border-radius: 50%; border: none; background: #d32f2f; color: #fff; font-size: 17px; cursor: pointer; flex-shrink: 0; }
  #gear { position: fixed; right: 10px; top: 74px; background: rgba(0,0,0,.25); border: none; color: #fff; border-radius: 50%; width: 30px; height: 30px; cursor: pointer; z-index: 5; }
  #convs { display: none; }
  .drawer { display: none; background: #fff; margin: 0 12px 8px; border-radius: 14px; padding: 12px; box-shadow: 0 2px 10px rgba(0,0,0,.15); font-size: 13px; max-height: 60vh; overflow-y: auto; }
  .drawer input, .drawer select, .drawer textarea { margin: 4px 0; padding: 8px; border-radius: 8px; border: 1px solid #cfd8dc; width: 100%; }
  .drawer button { margin-top: 6px; padding: 8px 12px; border-radius: 10px; border: none; background: #00684a; color: #fff; cursor: pointer; }
  .drawer .item { display: block; width: 100%; background: #f2f4f7; color: #222; margin: 4px 0; text-align: left; }
  .xbtn { background: #d32f2f !important; float: right; }
  #drop { border: 2px dashed #00855f; border-radius: 12px; padding: 14px; text-align: center; color: #00684a; background: #f2fbf6; margin: 6px 0; cursor: pointer; }
  #dlist { white-space: pre-wrap; background: #f7f9fa; border-radius: 8px; padding: 8px; margin-top: 6px; font-size: 12px; }
  .etiq { display: block; margin: 8px 0 2px; font-weight: 700; color: #00684a; }
  .ayuda { font-size: 11.5px; color: #667; margin-bottom: 4px; }
  .fb-captura { margin-top: 8px; border: 1px solid #cfd8dc; border-radius: 8px; padding: 8px; text-align: center; background: #f7f9fa; font-size: 11.5px; color: #556; }
  @media (max-width: 900px) { #side { display: none; } #convs { display: block; } }
  @media (min-width: 900px) {
    .bub { font-size: calc(16.5px * var(--fs, 1)); }
    header h1 { font-size: 21px; }
    header p { font-size: 13px; }
    #inp { font-size: calc(17px * var(--fs, 1)); padding: 14px 22px; }
    .msg { max-width: 70%; }
  }
</style>
</head>
<body>
<div id="toast"></div>
<div class="wrap">
  <aside id="side">
    <b id="sidet">🗂️ Conversaciones</b>
    <button id="sidenew">➕ Nueva conversación</button>
    <div id="lista"></div>
  </aside>
  <main>
    <header>
      <img src="/logo.png" alt="logo">
      <div><h1>UABCBot {FACULTAD_SIGLAS}</h1><p id="hsub">{FACULTAD_NOMBRE} de la UABC en Mexicali</p></div>
      <div class="langs">
        <button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button>
      </div>
      <div class="langs" style="margin-left:4px">
        <button id="fmenos" title="Letra más pequeña">A−</button><button id="fmas" title="Letra más grande">A+</button><button id="full" title="Pantalla completa">⛶</button>
      </div>
      <button id="convs" class="hbtn" title="Conversaciones">🗂️</button>
      <button id="user" class="hbtn" title="Tu cuenta">👤</button>
      <button id="logout" class="hbtn" title="Cerrar sesión">🚪</button>
      <button id="nuevo" class="hbtn" title="Nueva conversación">🧹</button>
    </header>
    <button id="gear" title="Personal autorizado">⚙️</button>
    <div id="cdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button><b id="sidet2">🗂️ Conversaciones</b><div id="lista2"></div></div>
    <div id="udrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b id="utitle">👤 Tu cuenta</b>
      <div id="who"></div>
      <input id="uusr" placeholder="Correo (usa @uabc.edu.mx si eres de la Facultad)">
      <input id="ukey" type="password" placeholder="Clave">
      <button id="ureg">✨ Registrarme</button>
      <button id="ulin">🔑 Entrar</button>
      <button id="uguest">👋 Seguir como invitado</button>
      <button id="uout">🚪 Cerrar sesión</button>
    </div>
    <div id="chat"></div>
    <div id="fbdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b id="fbtitle">🚩 Reportar respuesta no resuelta</b>
      <span class="etiq" id="fbarea_l">Área responsable</span>
      <select id="fbarea">
        <option>Admisión</option><option>CEC</option><option>Escolar/Escolaridad</option><option>Egresados/Bolsa de trabajo</option><option>Eventos</option><option>Otro</option>
      </select>
      <span class="etiq" id="fbcom_l">Cuéntanos qué faltó</span>
      <textarea id="fbcom" rows="3" placeholder="Ej. No me dijo el costo de inscripción al curso de inglés…"></textarea>
      <div id="fbprev" class="fb-captura">📸 Se adjuntará una captura de pantalla automática del chat.</div>
      <button id="fbsend">📨 Enviar al responsable</button>
    </div>
    <div id="drawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>🛠️ Panel de personal</b>
      <input id="clave" type="password" placeholder="Clave de acceso (Enter para entrar)">
      <button id="unlock">🔓 Entrar</button>
      <button id="salirp">🚪 Salir del panel</button>
      <div id="zona" style="display:none">
         <span class="etiq">👤 Tu identidad (se recuerda automáticamente)</span>
         <input id="admin_nombre" placeholder="Tu nombre completo" style="margin:4px 0;padding:8px;border-radius:8px;border:1px solid #cfd8dc;width:100%;">
         <input id="admin_correo" placeholder="Tu correo (@uabc.edu.mx)" style="margin:4px 0;padding:8px;border-radius:8px;border:1px solid #cfd8dc;width:100%;">
         <select id="admin_depto" style="margin:4px 0;padding:8px;border-radius:8px;border:1px solid #cfd8dc;width:100%;">
           <option value="">-- Selecciona tu departamento --</option>
           <option>Dirección</option><option>Subdirección</option>
           <option>Coordinación de Investigación y Posgrado</option>
           <option>Coordinación de Formación Profesional</option>
           <option>Coordinación de Extensión y Vinculación</option>
           <option>Administración</option><option>Titulación</option>
           <option>Servicio Social</option><option>Prácticas Profesionales</option>
           <option>Admisión</option><option>CEC</option><option>Egresados</option><option>Otro</option>
         </select>
         <span class="etiq">🔒 Visibilidad del contenido</span>
         <select id="fvis" style="margin:4px 0;padding:8px;border-radius:8px;border:1px solid #cfd8dc;width:100%;">
           <option value="publico">🌐 Público (todos lo ven)</option>
           <option value="interno">🔒 Solo comunidad UABC</option>
         </select>
        <span class="etiq">1️⃣ Categoría del aviso (usa "Clases" para info interna UABC)</span>
        <select id="fcat">
          <option>Avisos</option><option>Eventos</option><option>Suspensiones</option><option>Horarios</option><option>Exámenes</option><option>Convocatorias</option><option>TSU</option><option>PlanDeEstudios</option><option>CEC</option><option>Clases</option><option>Tareas</option><option>Internos</option>
        </select>
        <span class="etiq">2️⃣ Vigente hasta (opcional)</span>
        <input id="fvig" type="date">
        <span class="etiq">3️⃣ Elige o arrastra el archivo (TXT, PDF o imagen)</span>
        <div id="drop">📥 Arrastra aquí tu documento o póster<br><small>o toca para elegirlo</small></div>
        <input id="ffile" type="file" style="display:none">
        <span class="etiq">📝 Texto del póster (plan B recomendado para imágenes)</span>
        <div class="ayuda">Si subes una IMAGEN y el motor de visión está saturado, copia y pega aquí lo que dice el póster (evento, fecha, hora, lugar, costos) y se publicará al instante sin esperar.</div>
        <textarea id="ftexto" rows="4" placeholder="Ejemplo: Plática para Potenciales a Egresar. Martes 18 de agosto, 12:00 y 16:00 hrs, Sala de Usos Múltiples. Informes: Mtra. Dulce Rodríguez, egresados__idiomas__mxl@uabc.edu.mx"></textarea>
        <button id="fsubir">📤 Subir y publicar</button>
        <button id="nota">🎤 Grabar nota de voz</button>
        <button id="ldocs">🔄 Ver documentos</button>
        <button id="lfb">📨 Ver feedbacks</button>
        <button id="rep">📊 Reporte de uso</button>
        <div id="dlist"></div>
        <span class="etiq">🗑️ Borrar un documento</span>
        <input id="fdel" placeholder="Nombre del documento a borrar (Enter borra)">
        <button id="bdel">🗑️ Borrar</button>
        <div id="fest"></div>
      </div>
    </div>
    <div class="bar">
      <button id="mic">🎤</button>
      <input id="inp" placeholder="Escribe o dime tu pregunta…">
      <button id="send">➤</button>
      <button id="fb" title="¿No te resolvió? Repórtalo">🚩</button>
    </div>
  </main>
</div>
<script>
let hist = [], state = {pending:false, active:false}, langPref = "auto", rec = null, rec2 = null, chunks = [], currentId = uid(), droppedFile = null, thinkTimer = null, thinkSec = 0, toastTimer = null, lastPregunta = "", lastRespuesta = "", capturaPendiente = "", fontScale = 1;
let currentUser = localStorage.getItem('uabc_user') || "";
let currentRol = localStorage.getItem('uabc_rol') || "externo";
const chat = document.getElementById('chat'), inp = document.getElementById('inp');
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const BIENVENIDAS = {
  es: '👋 ¡Hola! Soy <b>UABCBot Idiomas</b>, el asistente de la Facultad de Idiomas de la UABC en Mexicali. Te atiendo en español, inglés o francés: <b>te leo o te escucho</b>. Toca una opción o escribe/dime tu pregunta.',
  en: '👋 Hi! I am <b>UABCBot Idiomas</b>, the assistant of the UABC Faculty of Languages in Mexicali. I serve you in Spanish, English or French: <b>I read you or listen to you</b>. Tap an option or type/say your question.',
  fr: '👋 Bonjour ! Je suis <b>UABCBot Idiomas</b>, l’assistant de la Faculté de Langues de l’UABC à Mexicali. Je t’aide en espagnol, anglais ou français : <b>je te lis ou je t’écoute</b>. Touche une option ou écris/dis ta question.'
};
const TXT_BIENVENIDAS = {
  es: '¡Hola! Soy UABCBot Idiomas, el asistente de la Facultad de Idiomas de la UABC en Mexicali. Te atiendo en español, inglés o francés: te leo o te escucho. Toca una opción, o escribe o dime tu pregunta.',
  en: 'Hi! I am UABCBot Idiomas, the assistant of the UABC Faculty of Languages in Mexicali. I serve you in Spanish, English or French: I read you or listen to you. Tap an option, or type or say your question.',
  fr: 'Bonjour ! Je suis UABCBot Idiomas, l’assistant de la Faculté de Langues de l’UABC à Mexicali. Je t’aide en espagnol, anglais ou français : je te lis ou je t’écoute. Touche une option, ou écris ou dis ta question.'
};
const NOTAS = {
  es: 'Personal docente: escribe o di "administración". Comunidad UABC: regístrate con tu correo @uabc.edu.mx para ver avisos de clases. Si una respuesta no te resuelve, toca 🚩.',
  en: 'Faculty staff: type or say "administración". UABC community: register with your @uabc.edu.mx email to see class notices. If an answer doesn’t help you, tap 🚩.',
  fr: 'Personnel : écris ou dis « administración ». Communauté UABC : inscris-toi avec ton courriel @uabc.edu.mx pour voir les avis de cours. Si une réponse ne t’aide pas, touche 🚩.'
};
const GUEST_MSG = {
  es: '👋 Invitado: sin memoria. Regístrate con 👤 para guardar tus conversaciones.',
  en: '👋 Guest: no memory. Register with 👤 to save your conversations.',
  fr: '👋 Invité : pas de mémoire. Inscris-toi avec 👤 pour garder tes conversations.'
};
const UI = {
  es: {sub: "Facultad de Idiomas de la UABC en Mexicali", side: "🗂️ Conversaciones", new: "➕ Nueva conversación", ph: "Escribe o dime tu pregunta…", utitle: "👤 Tu cuenta", reg: "✨ Registrarme", login: "🔑 Entrar", guest: "👋 Seguir como invitado", out: "🚪 Cerrar sesión", correo: "Correo (usa @uabc.edu.mx si eres de la Facultad)", clave: "Clave", fbtitle: "🚩 Reportar respuesta no resuelta", fbarea: "Área responsable", fbcom: "Cuéntanos qué faltó"},
  en: {sub: "Faculty of Languages of UABC in Mexicali", side: "🗂️ Conversations", new: "➕ New conversation", ph: "Type or say your question…", utitle: "👤 Your account", reg: "✨ Register", login: "🔑 Sign in", guest: "👋 Continue as guest", out: "🚪 Sign out", correo: "Email (use @uabc.edu.mx if you are UABC)", clave: "Password", fbtitle: "🚩 Report an unresolved answer", fbarea: "Responsible area", fbcom: "Tell us what was missing"},
  fr: {sub: "Faculté de Langues de l’UABC à Mexicali", side: "🗂️ Conversations", new: "➕ Nouvelle conversation", ph: "Écris ou dis ta question…", utitle: "👤 Ton compte", reg: "✨ M’inscrire", login: "🔑 Entrer", guest: "👋 Continuer en invité", out: "🚪 Sortir", correo: "Courriel (utilise @uabc.edu.mx si eres de la Facultad)", clave: "Mot de passe", fbtitle: "🚩 Signaler une réponse non résolue", fbarea: "Zone responsable", fbcom: "Dis-nous ce qui a manqué"}
};
const WHO = {
  es: {interno: ' · ✅ comunidad UABC (ve avisos de clases)', externo: ' · público general', guest: '👋 Modo invitado (público general): sin memoria ni avisos internos.'},
  en: {interno: ' · ✅ UABC community (sees class notices)', externo: ' · general public', guest: '👋 Guest mode (general public): no memory, no internal notices.'},
  fr: {interno: ' · ✅ communauté UABC (voit les avis de cours)', externo: ' · public général', guest: '👋 Mode invité (public général) : pas de mémoire ni avis internes.'}
};
const OPTS_BASE = {
  "¿Cuántos créditos necesito para titularme en Traducción?": {es:"💳 Créditos para titularme", en:"💳 Credits to graduate", fr:"💳 Crédits pour diplômer"},
  "¿Cuánto cuesta inscribirme a las clases de inglés?": {es:"💰 Costo de clases de inglés", en:"💰 English class cost", fr:"💰 Coût des cours d'anglais"},
  "¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?": {es:"🎓 Requisitos de admisión", en:"🎓 Admission requirements", fr:"🎓 Conditions d'admission"},
  "¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?": {es:"🏛️ Carreras y TSU", en:"🏛️ Degrees & TSU", fr:"🏛️ Licences & TSU"}
};
function uid(){ return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2,7); }
function langUI(){ return (langPref in BIENVENIDAS) ? langPref : 'es'; }
function applyFont(){ document.documentElement.style.setProperty('--fs', fontScale); }
function applyLang(L){
  const u = UI[L] || UI.es;
  document.getElementById('hsub').innerText = u.sub;
  document.getElementById('sidet').innerText = u.side;
  document.getElementById('sidet2').innerText = u.side;
  document.getElementById('sidenew').innerText = u.new;
  document.getElementById('inp').placeholder = u.ph;
  document.getElementById('utitle').innerText = u.utitle;
  document.getElementById('ureg').innerText = u.reg;
  document.getElementById('ulin').innerText = u.login;
  document.getElementById('uguest').innerText = u.guest;
  document.getElementById('uout').innerText = u.out;
  document.getElementById('uusr').placeholder = u.correo;
  document.getElementById('ukey').placeholder = u.clave;
  document.getElementById('fbtitle').innerText = u.fbtitle;
  document.getElementById('fbarea_l').innerText = u.fbarea;
  document.getElementById('fbcom_l').innerText = u.fbcom;
}
function avisar(msg, tipo){
  const t = document.getElementById('toast');
  t.innerText = msg;
  t.style.background = tipo === 'error' ? '#d32f2f' : (tipo === 'ok' ? '#00684a' : '#f7941d');
  t.style.display = 'block';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = 'none'; }, 7000);
}
function bubble(role, text, audio){
  const d = document.createElement('div'); d.className = 'msg ' + role;
  let h = '<div class="bub">' + esc(text) + '</div>';
  if (audio) h += '<audio controls src="' + audio + '"></audio>';
  d.innerHTML = h; chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  return d;
}
async function welcome(){
  const L = langUI();
  applyLang(L);
  let opts = Object.keys(OPTS_BASE).map(q => ({q, t: OPTS_BASE[q][L]}));
  try {
    const d = await (await fetch('/api/topfaq')).json();
    const extras = (d || []).filter(x => !OPTS_BASE[x.q])
      .map(x => ({q: x.q, t: "🔥 " + (x.q.length > 40 ? x.q.slice(0,40) + "…" : x.q)}));
    opts = opts.concat(extras.slice(0, 4));
  } catch(e) {}
  const d = document.createElement('div'); d.className = 'msg bot';
  d.innerHTML = '<div class="bub">' + BIENVENIDAS[L] + '<div class="opts">'
    + opts.map(o => '<button data-q="' + esc(o.q) + '">' + esc(o.t) + '</button>').join('')
    + '</div><span class="nota">' + NOTAS[L] + '</span></div>';
  chat.appendChild(d);
  d.querySelectorAll('[data-q]').forEach(b => b.onclick = () => send(b.dataset.q));
  try {
    const a = await (await fetch('/api/tts?lang=' + L + '&texto=' + encodeURIComponent(TXT_BIENVENIDAS[L]))).json();
    if (a.url) {
      const au = document.createElement('audio');
      au.controls = true; au.src = a.url;
      d.querySelector('.bub').appendChild(au);
    }
  } catch(e) {}
  chat.scrollTop = chat.scrollHeight;
}
function thinking(){
  removeThink();
  const d = document.createElement('div'); d.className = 'msg bot think'; d.id = 'think';
  d.innerHTML = '<div class="bub">🤔 Trabajando en tu respuesta… <span id="tsec">0</span> s</div>';
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  thinkSec = 0;
  thinkTimer = setInterval(() => { thinkSec++; const e = document.getElementById('tsec'); if (e) e.textContent = thinkSec; }, 1000);
}
function removeThink(){
  if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null; }
  const t = document.getElementById('think'); if (t) t.remove();
}
function refreshWho(){
  const L = langUI(); const w = WHO[L] || WHO.es;
  document.getElementById('who').innerText = currentUser ? '✅ ' + currentUser + (currentRol === 'interno' ? w.interno : w.externo) : w.guest;
}
function doLogout(){
  currentUser = ""; currentRol = "externo";
  localStorage.removeItem('uabc_user'); localStorage.removeItem('uabc_rol');
  refreshWho(); loadList();
  document.getElementById('udrawer').style.display = 'none';
  avisar(langUI()==='es' ? '👋 Sesión cerrada.' : (langUI()==='en' ? '👋 Signed out.' : '👋 Session fermée.'));
}
function saveConv(){
  if (!currentUser) return;
  const titulo = ((hist.find(m => m.role === 'user') || {}).content || 'Nueva conversación').slice(0, 40);
  fetch('/api/conv/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: currentId, user: currentUser, titulo, msgs: hist})}).then(() => loadList());
}
async function loadList(){
  if (!currentUser) {
    const msg = '<small>' + (GUEST_MSG[langUI()] || GUEST_MSG.es) + '</small>';
    document.getElementById('lista').innerHTML = msg;
    document.getElementById('lista2').innerHTML = msg;
    return;
  }
  const d = await (await fetch('/api/conv/list?user=' + encodeURIComponent(currentUser))).json();
  const html = d.map(c => '<button class="item" data-id="' + c.id + '">' + esc(c.titulo) + '</button>').join('');
  document.getElementById('lista').innerHTML = html || '<small>Sin conversaciones aún.</small>';
  document.getElementById('lista2').innerHTML = html || '<small>Sin conversaciones aún.</small>';
  document.querySelectorAll('[data-id]').forEach(b => b.onclick = () => openConv(b.dataset.id));
}
async function openConv(id){
  const d = await (await fetch('/api/conv/get?id=' + id)).json();
  if (!d.msgs) return;
  currentId = id; hist = d.msgs; state = {pending:false, active:false};
  chat.innerHTML = '';
  hist.forEach(m => bubble(m.role, m.content, m.audio));
  document.getElementById('cdrawer').style.display = 'none';
}
function nueva(){
  currentId = uid(); hist = []; state = {pending:false, active:false};
  chat.innerHTML = ''; welcome(); loadList();
  document.getElementById('cdrawer').style.display = 'none';
}
async function send(msg){
  if (!msg.trim()) return;
  const esClave = state.pending;
  const el = bubble('user', msg);
  hist.push({role:'user', content: esClave ? '••••••' : msg});
  if (esClave) setTimeout(() => { el.querySelector('.bub').textContent = '🔑 ••••••'; }, 30000);
  inp.value = '';
  lastPregunta = msg;
  thinking();
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg, hist: hist.slice(-7), state, lang: langPref, rol: currentRol})});
  const d = await r.json(); removeThink(); state = d.state;
  lastRespuesta = d.reply;
  if (langPref === 'auto' && d.lang) applyLang(d.lang);
  hist.push({role:'assistant', content: d.reply, audio: d.audio}); bubble('bot', d.reply, d.audio);
  saveConv();
}
async function loadDocs(){
  const d = await (await fetch('/api/docs')).json();
  document.getElementById('dlist').innerText = (d.docs || []).join('\\n') || 'Sin documentos.';
}
document.getElementById('send').onclick = () => send(inp.value);
inp.onkeydown = e => { if (e.key === 'Enter') send(inp.value); };
document.getElementById('nuevo').onclick = nueva;
document.getElementById('sidenew').onclick = nueva;
document.getElementById('convs').onclick = () => { const d = document.getElementById('cdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; loadList(); };
document.getElementById('user').onclick = () => { const d = document.getElementById('udrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; refreshWho(); };
document.getElementById('logout').onclick = doLogout;
document.getElementById('fmas').onclick = () => { fontScale = Math.min(1.6, fontScale + 0.1); applyFont(); avisar('🔍 ' + Math.round(fontScale*100) + '%'); };
document.getElementById('fmenos').onclick = () => { fontScale = Math.max(0.8, fontScale - 0.1); applyFont(); avisar('🔍 ' + Math.round(fontScale*100) + '%'); };
document.getElementById('full').onclick = () => {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen();
  else document.exitFullscreen();
};
document.getElementById('fb').onclick = async () => {
  if (!lastRespuesta) { avisar('⚠️ Aún no hay respuestas que reportar.', 'error'); return; }
  try {
    const canvas = await html2canvas(chat, {backgroundColor: '#eef1f4', scale: 1, useCORS: true, logging: false});
    capturaPendiente = canvas.toDataURL('image/png');
    document.getElementById('fbprev').innerHTML = '📸 Captura lista (' + Math.round(capturaPendiente.length/1024) + ' KB). Se adjuntará al enviar.';
  } catch(e) {
    capturaPendiente = "";
    document.getElementById('fbprev').innerText = '⚠️ No se pudo capturar la pantalla, pero el reporte se enviará igual.';
  }
  const d = document.getElementById('fbdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block';
};
document.getElementById('fbsend').onclick = async () => {
  avisar('⏳ Enviando reporte con captura...');
  await fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
    pregunta: lastPregunta, respuesta: lastRespuesta,
    comentario: document.getElementById('fbcom').value,
    area: document.getElementById('fbarea').value,
    captura: capturaPendiente
  })});
  document.getElementById('fbcom').value = '';
  document.getElementById('fbdrawer').style.display = 'none';
  capturaPendiente = "";
  avisar('📨 Reporte y captura enviados al responsable. ¡Gracias!', 'ok');
};
document.getElementById('ureg').onclick = async () => {
  const d = await (await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; currentRol = d.rol || 'externo';
  localStorage.setItem('uabc_user', currentUser); localStorage.setItem('uabc_rol', currentRol);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar(currentRol === 'interno' ? '✅ Bienvenido, ' + currentUser + '. Verás avisos internos de clases.' : '✅ Bienvenido, ' + currentUser + '.', 'ok');
};
document.getElementById('ulin').onclick = async () => {
  const d = await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; currentRol = d.rol || 'externo';
  localStorage.setItem('uabc_user', currentUser); localStorage.setItem('uabc_rol', currentRol);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('✅ ' + currentUser + (currentRol === 'interno' ? ' (comunidad UABC)' : ''), 'ok');
};
document.getElementById('uguest').onclick = doLogout;
document.getElementById('uout').onclick = doLogout;
[['Lauto','auto'],['Les','es'],['Len','en'],['Lfr','fr']].forEach(([id, v]) => {
  document.getElementById(id).onclick = e => {
    langPref = v;
    document.querySelectorAll('.langs button').forEach(x => x.classList.remove('on'));
    e.target.classList.add('on');
    applyLang(langUI()); refreshWho(); loadList();
    if (!hist.length) { chat.innerHTML = ''; welcome(); }
    else avisar(v === 'auto' ? ' AUTO: español por defecto; si te leo o escucho en otro idioma, todo cambia a ese idioma.' : '🌐 ' + v.toUpperCase());
  };
});
const drop = document.getElementById('drop');
function marcarArchivo(f){
  droppedFile = f;
  drop.innerHTML = '📎 ' + esc(f.name);
  avisar('📎 ' + f.name + ' → pulsa "📤 Subir y publicar".');
}
drop.onclick = () => document.getElementById('ffile').click();
drop.ondragover = e => e.preventDefault();
drop.ondrop = e => { e.preventDefault(); if (e.dataTransfer.files[0]) marcarArchivo(e.dataTransfer.files[0]); };
document.getElementById('ffile').onchange = e => { if (e.target.files[0]) marcarArchivo(e.target.files[0]); };
const mic = document.getElementById('mic');
mic.onclick = async () => {
  if (rec && rec.state === 'recording') { rec.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  chunks = []; rec = new MediaRecorder(stream);
  rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = async () => {
    stream.getTracks().forEach(t => t.stop()); mic.classList.remove('rec');
    thinking();
    const fd = new FormData();
    fd.append('audio', new Blob(chunks, {type:'audio/webm'}), 'voz.webm');
    fd.append('hist', JSON.stringify(hist.slice(-7)));
    fd.append('state', JSON.stringify(state));
    fd.append('lang', langPref);
    fd.append('rol', currentRol);
    const d = await (await fetch('/api/voice', {method:'POST', body: fd})).json();
    removeThink(); state = d.state;
    if (langPref === 'auto' && d.lang) applyLang(d.lang);
    if (d.texto) { bubble('user', '🎤 ' + d.texto); hist.push({role:'user', content: d.texto}); lastPregunta = d.texto; }
    if (d.reply) { bubble('bot', d.reply, d.audio); hist.push({role:'assistant', content: d.reply, audio: d.audio}); lastRespuesta = d.reply; }
    saveConv();
  };
  rec.start(); mic.classList.add('rec');
  avisar('🎤 Grabando… toca el micrófono para terminar.');
};
document.getElementById('gear').onclick = () => { const d = document.getElementById('drawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; };
document.getElementById('salirp').onclick = () => { state = {pending:false, active:false}; document.getElementById('drawer').style.display = 'none'; document.getElementById('zona').style.display = 'none'; };
document.getElementById('clave').onkeydown = e => { if (e.key === 'Enter') document.getElementById('unlock').click(); };
document.getElementById('fdel').onkeydown = e => { if (e.key === 'Enter') document.getElementById('bdel').click(); };
document.getElementById('unlock').onclick = async () => {
  const r = await fetch('/api/unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})});
  const d = await r.json();
  document.getElementById('zona').style.display = d.ok ? 'block' : 'none';
  if (d.ok) { loadDocs(); avisar('✅ Panel de personal abierto.', 'ok'); }
            // Load saved identity
            const savedId = JSON.parse(localStorage.getItem('admin_identidad') || '{}');
            if (savedId.nombre) document.getElementById('admin_nombre').value = savedId.nombre;
            if (savedId.correo) document.getElementById('admin_correo').value = savedId.correo;
            if (savedId.depto) document.getElementById('admin_depto').value = savedId.depto;
  else avisar('❌ Clave incorrecta.', 'error');
};
document.getElementById('fsubir').onclick = async () => {
  const f = document.getElementById('ffile').files[0] || droppedFile;
  if (!f && !document.getElementById('ftexto').value.trim()) { avisar('⚠️ Elige un archivo o pega el texto en 📝.', 'error'); return; }
  avisar('⏳ Procesando y publicando…');
  const nombre = document.getElementById('admin_nombre').value.trim();
  const correo = document.getElementById('admin_correo').value.trim();
  const depto = document.getElementById('admin_depto').value;
  if (!nombre || !correo || !depto) { avisar('⚠️ Completa tu identidad antes de subir.', 'error'); return; }
  localStorage.setItem('admin_identidad', JSON.stringify({nombre, correo, depto})); 
  const fd = new FormData();
  if (f) fd.append('archivo', f);
  fd.append('categoria', document.getElementById('fcat').value);
  fd.append('vigencia', document.getElementById('fvig').value);
  fd.append('reemplazar', '0');
  fd.append('texto_manual', document.getElementById('ftexto').value);
  fd.append('responsable_nombre', nombre);
  fd.append('responsable_correo', correo);
  fd.append('departamento', depto);
  fd.append('visibilidad', document.getElementById('fvis').value);
  const d = await (await fetch('/api/upload', {method:'POST', body: fd})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.startsWith('✅') ? 'ok' : 'error');
  loadDocs();
}
document.getElementById('ldocs').onclick = loadDocs;
document.getElementById('lfb').onclick = async () => {
  const d = await (await fetch('/api/feedback/list?clave=' + encodeURIComponent(document.getElementById('clave').value))).json();
  document.getElementById('fest').innerText = (d.items || []).join('\\n------------------\\n');
  avisar('📨 Feedbacks listados abajo.', 'ok');
};
document.getElementById('bdel').onclick = async () => {
  const d = await (await fetch('/api/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value, nombre: document.getElementById('fdel').value})})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.startsWith('🗑️') ? 'ok' : 'error');
  loadDocs();
};
document.getElementById('nota').onclick = async () => {
  if (rec2 && rec2.state === 'recording') { rec2.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  let ch = []; rec2 = new MediaRecorder(stream);
  rec2.ondataavailable = e => ch.push(e.data);
  rec2.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    avisar('⏳ Transcribiendo y publicando…');
    const fd = new FormData();
    fd.append('audio', new Blob(ch, {type:'audio/webm'}), 'nota.webm');
    fd.append('categoria', document.getElementById('fcat').value);
    const d = await (await fetch('/api/voice_note', {method:'POST', body: fd})).json();
    document.getElementById('fest').innerText = d.estado;
    avisar(d.estado, d.estado.startsWith('✅') ? 'ok' : 'error');
    loadDocs();
  };
  rec2.start();
  avisar('🔴 Grabando nota… toca de nuevo para terminar.');
};
document.getElementById('rep').onclick = async () => {
  const d = await (await fetch('/api/report', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})})).json();
  if (d.error) { avisar(d.error, 'error'); return; }
  document.getElementById('fest').innerText = '📊 Total: ' + d.total + ' · Hoy: ' + d.hoy + ' · Idiomas: ' + JSON.stringify(d.idiomas)
    + '\\n\\n🔥 Más frecuentes:\\n' + d.top.map((x, i) => (i+1) + '. ' + x[0] + ' (' + x[1] + ')').join('\\n');
  avisar('📊 Reporte listo.', 'ok');
};
applyFont(); welcome(); loadList(); refreshWho(); inp.focus();
</script>
</body>
</html>
"""

@app.get("/")
async def inicio():
    pagina_render = PAGINA.replace("{FACULTAD_SIGLAS}", FACULTAD_SIGLAS).replace("{FACULTAD_NOMBRE}", FACULTAD_NOMBRE)
    return HTMLResponse(pagina_render)

@app.get("/api/cache/clear_all")
async def cache_clear_all():
    try:
        os.remove(CACHE)
    except Exception:
        pass
    return {"ok": True, "mensaje": "Caché eliminada. Reinicia el bot para aplicar."}
@app.get("/api/sistemas/estado")
async def sistemas_estado(clave: str = ""):
    if clave != CLAVE_SISTEMAS:
        return {"error": "Clave incorrecta"}
    from datetime import datetime as _dt
    try:
        total_uso = len(leer_uso())
    except Exception:
        total_uso = 0
    return {
        "estado": "activo",
        "version_web_app": "v34",
        "timestamp": _dt.now().isoformat(),
        "total_preguntas_registradas": total_uso,
        "repo_backup": GH_REPO,
        "cron_respaldo": "diario 3:30 AM",
        "arquitectura": "FastAPI + Qdrant Cloud + SQLite",
    }

@app.get("/api/sistemas/respaldo_manual")
async def sistemas_respaldo_manual(clave: str = ""):
    if clave != CLAVE_SISTEMAS:
        return {"error": "Clave incorrecta"}
    try:
        subidos = respaldo_github_completo()
        return {"ok": True, "archivos_subidos": subidos, "mensaje": f"Respaldo subido a GitHub: {subidos} archivos"}
    except Exception as e:
        return {"ok": False, "error": f"Error: {e}"}

@app.get("/api/sistemas/respaldo")
async def sistemas_respaldo(clave: str = ""):
    if clave != CLAVE_SISTEMAS:
        return {"error": "Clave incorrecta"}
    try:
        zip_bytes = crear_zip_respaldo()
        from fastapi.responses import Response
        from datetime import datetime as _dt
        nombre = f"respaldo_uabc_{_dt.now().strftime('%Y%m%d_%H%M')}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={nombre}"},
        )
    except Exception as e:
        return {"error": f"Error generando ZIP: {e}"}

@app.get("/api/vectorial/stats")
async def vectorial_stats():
    try:
        c = get_chroma()
        return {"fragmentos_indexados": c.count(), "estado": "ok"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))


# ===== NOTA DE VERSIÓN =====
# Fecha: 2026-10-06_1908
# Cambios: Fix detección francés con word-boundary + Fix referencia _indexar_archivo_robusto
# ===========================
