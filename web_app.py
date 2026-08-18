import os
import re
import uuid
import json
import time
import base64
import asyncio
import hashlib
import secrets
import tempfile
import requests
from datetime import datetime, date, timedelta
from collections import Counter
from google import genai as genai_lib
from google.genai import types as gtypes
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn

# ================= CONFIGURACIÓN =================
BASE = os.path.dirname(os.path.abspath(__file__))
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
CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "fimxl2026")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPO", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_KEY_2 = os.environ.get("GEMINI_API_KEY_2", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LOGO = os.path.join(BASE, "logo.png")
LOGO_URL = "https://raw.githubusercontent.com/JACacho/uabc-idiomas-bot/main/logo.png"
for d in (AUDIOS, CARPETA, CONVS, IMGS, FEEDBACK, CAPTURAS):
    os.makedirs(d, exist_ok=True)

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

# ================= CEREBRO =================
def fecha_hoy_es():
    n = datetime.now()
    return f"{DIAS[n.weekday()]} {n.day} de {MESES[n.month]} de {n.year}"

def detectar_idioma(texto):
    t = (texto or "").lower()
    fr_st = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplôm", "traduction", "salut", "crédit", "je ", "étud", "etud", "français", "francais", "voud", "veux", "voaux", "quel", "quelle", "aime", "les ", "des ", "anglais"]
    en_st = ["hello", "thank", "how", "many", "credit", "degree", "translation", "what", "when", "where", "i ", "would", "like", "to ", "study", "french", "english", "do ", "you", "for", "me", "is ", "are ", "the ", "my ", "can", "help"]
    hf = sum(1 for w in fr_st if w in t)
    he = sum(1 for w in en_st if w in t)
    if hf >= 2 and hf > he:
        return "fr"
    if he >= 2 and he > hf:
        return "en"
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
    return set(re.findall(r"[a-záéíóúñü]+", (t or "").lower()))

def _es_valida(t):
    if not t:
        return False
    if t.strip().endswith("?") and len(t) < 160:
        return False
    return True

def _cargar_docs():
    docs = {}
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                try:
                    with open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore") as f:
                        docs[fn] = _limpiar_doc(f.read())
                except Exception:
                    continue
    return docs

def cargar_contexto(pregunta):
    partes = []
    try:
        with open(MANUAL, encoding="utf-8", errors="ignore") as f:
            partes.append(_limpiar_doc(f.read()))
    except Exception:
        pass
    docs = _cargar_docs()
    hoy = date.today()
    horizonte = hoy + timedelta(days=14)
    recientes = sorted(docs.keys(), reverse=True)[:2]
    frescos = [fn for fn, t in docs.items() if any(hoy <= f <= horizonte for f in _fechas_doc(t))][:3]
    qt = _tokens(pregunta)
    scored = sorted(((len(qt & _tokens(t)), fn) for fn, t in docs.items()), reverse=True)
    seleccion = []
    for fn in recientes + frescos + [fn for _, fn in scored[:2]]:
        if fn not in seleccion:
            seleccion.append(fn)
    for fn in seleccion[:5]:
        partes.append(docs[fn])
    return "\n\n".join(partes)[:12000]

def respuesta_de_documentos(pregunta):
    docs = _cargar_docs()
    if not docs:
        return ""
    hoy = date.today()
    horizonte = hoy + timedelta(days=14)
    p = (pregunta or "").lower()
    if any(k in p for k in ("semana", "evento", "hoy", "mañana", "pronto", "avisos", "hay")):
        frescos = [t for t in docs.values() if any(hoy <= f <= horizonte for f in _fechas_doc(t))][:2]
        if frescos:
            return "📅 Según los avisos oficiales más recientes de la Facultad:\n\n" + "\n\n".join(t[:500] for t in frescos)
    qt = _tokens(pregunta)
    scored = sorted(((len(qt & _tokens(t)), t) for t in docs.values()), reverse=True)
    if scored and scored[0][0] >= 3:
        return "Según la información oficial de la Facultad: " + scored[0][1][:600]
    return ""

def sistema_prompt(contexto):
    return (
        f"Hoy es {fecha_hoy_es()}. Eres UABCBot Idiomas, asistente virtual de la Facultad de Idiomas de la UABC en Mexicali. "
        "Responde SIEMPRE en el idioma de la pregunta y en párrafos naturales, claros y concisos (máximo ~120 palabras salvo que pidan detalle). "
        "NUNCA repitas la pregunta del usuario ni respondas con otra pregunta; entrega siempre información concreta. "
        "FECHAS Y EVENTOS: si preguntan por 'hoy', 'mañana', 'esta semana', 'la próxima semana' o 'pronto', menciona PRIMERO los eventos y avisos con fecha dentro de los próximos 14 días a partir de hoy (con fecha, hora y lugar si los tienes); NUNCA cites fechas que ya pasaron ni te contradigas; si no hay eventos próximos, dilo y menciona la siguiente fecha importante futura. "
        "REGLAS DE ORO: responde ÚNICAMENTE a la pregunta del usuario; NUNCA reproduzcas el contexto como lista de preguntas y respuestas; "
        "NUNCA copies nombres de archivo, encabezados con ===, ni palabras como DOCUMENTO o CONTEXTO; reformula con tus palabras y usa solo datos disponibles. "
        "Si la información no aparece, sugiere contactar a la Facultad: tel. 686-689-0825, idiomas.mxl@uabc.edu.mx, idiomas.mxl.uabc.mx. "
        f"\nINFORMACIÓN DISPONIBLE:\n{contexto}"
    )

def llamar_gemini(cliente, sp, hist, pregunta):
    if not cliente:
        return None
    try:
        contents = []
        for m in hist:
            contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": pregunta}]})
        r = cliente.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config={"system_instruction": sp, "temperature": 0.1},
        )
        return (r.text or "").strip() or None
    except Exception:
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

def _vision_gemini(cliente, data, mime, prompt):
    if not cliente:
        return ""
    for modelo in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"):
        try:
            r = cliente.models.generate_content(
                model=modelo,
                contents=[gtypes.Part(inline_data=gtypes.Blob(data=data, mime_type=mime)), prompt],
            )
            t = (r.text or "").strip()
            if t:
                return t
        except Exception:
            continue
    return ""

def extraer_imagen(data, mime="image/jpeg"):
    errs = []
    for i, cliente in enumerate((cliente_gemini, cliente_gemini2), 1):
        t = _vision_gemini(cliente, data, mime, PROMPT_POSTER)
        if t:
            return t, ""
        errs.append(f"Gemini{i} sin cuota de imagen")
    b64 = base64.b64encode(data).decode()
    t = llamar_vision(GROQ_URL, GROQ_KEY, ["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"], b64, mime, PROMPT_POSTER)
    if t:
        return t, ""
    errs.append("Groq visión no disponible")
    t = llamar_vision(OR_URL, OR_KEY, ["meta-llama/llama-3.2-90b-vision-instruct:free", "google/gemini-2.0-flash-001", "google/gemini-2.0-flash-exp:free"], b64, mime, PROMPT_POSTER)
    if t:
        return t, ""
    errs.append("OpenRouter visión no disponible")
    return "", " | ".join(errs)

def probar_vision():
    out = {}
    for i, cliente in enumerate((cliente_gemini, cliente_gemini2), 1):
        out[f"gemini{i}"] = bool(_vision_gemini(cliente, IMG_PRUEBA, "image/png", "Describe la imagen en una palabra."))
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
    return not (texto.startswith("⚠️") or texto.startswith("📅") or texto.startswith("Según la información oficial") or len(texto) < 60 or "ayudarte hoy" in t or "no está en el contexto" in t or "===" in texto or "documento " in t or "manual de conocimiento" in t or len(texto) > 900)

def responder(pregunta, historial, lang_pref="auto"):
    p = (pregunta or "").lower()
    lang_detect = detectar_idioma(pregunta)
    lang = lang_pref if lang_pref in ("es", "en", "fr") else lang_detect
    for claves, trad in MEMORIA_OFICIAL:
        if any(k in p for k in claves):
            return trad.get(lang, trad["es"]), lang
    clave = p.strip()[:120]
    cache = _cargar_cache()
    if clave in cache:
        return cache[clave][0], cache[clave][1]
    contexto = cargar_contexto(pregunta)
    sp = sistema_prompt(contexto)
    suf = {"es": " (Responde en español, conciso.)", "en": " (Answer in English, concise.)", "fr": " (Réponds en français, concis.)"}[lang]
    pregunta_final = pregunta + suf
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    # 🔥 DeepSeek V4 Flash 0731 como motor #1 (el más fuerte en Academia, baratísimo)
    texto = llamar_openai(sp, hist, pregunta_final, OR_URL, OR_KEY, ["deepseek/deepseek-v4-flash:free", "deepseek/deepseek-chat-v3.1:free", "meta-llama/llama-3.3-70b-instruct:free"])
    if not _es_valida(texto):
        texto = llamar_gemini(cliente_gemini, sp, hist, pregunta_final)
    if not _es_valida(texto):
        texto = llamar_gemini(cliente_gemini2, sp, hist, pregunta_final)
    if not _es_valida(texto):
        texto = llamar_openai(sp, hist, pregunta_final, GROQ_URL, GROQ_KEY, ["llama-3.3-70b-versatile"])
    if not _es_valida(texto):
        fb = respuesta_de_documentos(pregunta)
        if fb:
            return fb, lang
    if not _es_valida(texto):
        texto = "⚠️ Los motores de IA están saturados en este momento. Intenta de nuevo en unos segundos."
    texto = re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto).strip()
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
    for cliente in (cliente_gemini, cliente_gemini2):
        if not cliente:
            continue
        for mime in ("audio/webm", "audio/wav", "audio/mp3", "audio/ogg"):
            try:
                r = cliente.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        gtypes.Part(inline_data=gtypes.Blob(data=audio_bytes, mime_type=mime)),
                        "Transcribe textualmente este audio (español, inglés o francés). Devuelve solo la transcripción.",
                    ],
                )
                t = (r.text or "").strip()
                if t:
                    return t, detectar_idioma(t)
            except Exception:
                continue
    t = transcribir_groq(audio_bytes)
    if t:
        return t, detectar_idioma(t)
    return "", "es"

async def generar_voz(texto, lang):
    try:
        import edge_tts
        voz = VOCES.get(lang, VOCES["es"])
        ruta = os.path.join(tempfile.gettempdir(), "respuesta_uabc.mp3")
        c = edge_tts.Communicate(texto, voz)
        await c.save(ruta)
        return ruta
    except Exception:
        return None

# ================= SERVICIOS =================
app = FastAPI()

FAQ = [
    (["credito", "titular", "titul"], "¿Cuántos créditos necesito para titularme en Traducción?"),
    (["horario", "cec"], "¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?"),
    (["admision", "requisito", "inscri"], "¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?"),
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
    for claves, canonica in FAQ:
        if any(k in t for k in claves) and len(t) < 90:
            return canonica
    return texto or ""

def limpiar_tags(texto):
    return re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto or "").strip()

def github_subir(ruta_repo, contenido_bytes, es_binario=False):
    if not GH_TOKEN or not GH_REPO:
        return "(sin respaldo GitHub)"
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=15)
        contenido_b64 = base64.b64encode(contenido_bytes).decode() if isinstance(contenido_bytes, (bytes, bytearray)) else base64.b64encode(contenido_bytes.encode("utf-8")).decode()
        data = {"message": f"bot: actualiza {ruta_repo}", "content": contenido_b64}
        if r.status_code == 200 and r.json().get("sha"):
            data["sha"] = r.json()["sha"]
        q = requests.put(url, json=data, headers=headers, timeout=25)
        return "☁️ Respaldo permanente en GitHub listo." if q.status_code in (200, 201) else "⚠️ No se pudo respaldar en GitHub."
    except Exception:
        return "⚠️ No se pudo respaldar en GitHub."

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
        with open(USO, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(), "texto": texto, "lang": lang, "via": via}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def leer_uso():
    try:
        with open(USO, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception:
        return []

def guardar_aviso(texto, categoria="Avisos"):
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: sin límite ===\n"
    contenido = cab + texto
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(contenido)
    return nuevo, github_subir(f"datos_bot/{nuevo}", contenido.encode("utf-8"))

def extraer_texto(ruta, nombre):
    if nombre.lower().endswith(".pdf"):
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        return "\n".join((p.extract_text() or "") for p in lector.pages)
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        return f.read()

def router(msg, hist, state, lang_pref):
    state = state or {"pending": False, "active": False}
    texto = (msg or "").strip()
    if state.get("pending"):
        state["pending"] = False
        if texto == CLAVE_ADMIN:
            state["active"] = True
            return "✅ Acceso concedido, profe. Escribe tu aviso tal cual (o usa el panel ⚙️ para documentos, pósters y notas de voz). Escribe SALIR para cerrar.", None, state
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
        respuesta, lang = responder(pregunta, hist or [], lang_pref)
    except Exception:
        respuesta, lang = responder(pregunta, [], lang_pref)
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
    users[u] = {"salt": salt, "hash": _hash(c, salt)}
    _jdump(USERS, users)
    return {"ok": True, "usuario": u}

@app.post("/api/login")
async def api_login(req: Request):
    d = await req.json()
    u = (d.get("usuario") or "").strip().lower()
    c = d.get("clave") or ""
    users = _jload(USERS, {})
    rec = users.get(u)
    if not rec or rec["hash"] != _hash(c, rec["salt"]):
        return {"ok": False, "error": "Usuario o clave incorrectos."}
    return {"ok": True, "usuario": u}

@app.post("/api/chat")
async def api_chat(req: Request):
    d = await req.json()
    st = d.get("state") or {}
    if not (st.get("active") or st.get("pending")):
        log_uso(d.get("msg", ""), d.get("lang", "auto"), "texto")
    try:
        respuesta, lang, state = router(d.get("msg"), d.get("hist"), st, d.get("lang", "auto"))
        audio = await producir_audio(respuesta, lang)
    except Exception as e:
        respuesta = f"⚠️ Error interno: {type(e).__name__}: {e}"
        audio = None
        state = st
        lang = "es"
    return {"reply": respuesta, "audio": audio, "state": state, "lang": lang}

@app.post("/api/voice")
async def api_voice(audio: UploadFile = File(...), hist: str = Form("[]"), state: str = Form("{}"), lang: str = Form("auto")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"texto": "", "reply": "⚠️ No logré escuchar bien. Intenta de nuevo más cerca del micrófono.", "audio": None, "state": state, "lang": "es"}
    st = json.loads(state)
    if not (st.get("active") or st.get("pending")):
        log_uso(texto, lang, "voz")
    respuesta, lang2, state2 = router(texto, json.loads(hist), st, lang)
    aud = await producir_audio(respuesta, lang2)
    return {"texto": texto, "reply": respuesta, "audio": aud, "state": state2, "lang": lang2}

@app.post("/api/voice_note")
async def voice_note(audio: UploadFile = File(...), categoria: str = Form("Avisos")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"estado": "⚠️ No logré escuchar la nota."}
    nuevo, resp = guardar_aviso(texto, categoria)
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
    c = Counter(normalizar_faq(l["texto"]) for l in leer_uso() if l.get("texto"))
    return [{"q": q, "n": n} for q, n in c.most_common(4)]

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
async def api_upload(archivo: UploadFile = File(None), categoria: str = Form("Avisos"), vigencia: str = Form(""), reemplazar: str = Form("0"), texto_manual: str = Form("")):
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
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia or 'sin límite'} ===\n"
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(cab + texto)
    resp = github_subir(f"datos_bot/{nuevo}", (cab + texto).encode("utf-8"))
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
<title>UABCBot Idiomas — Facultad de Idiomas de la UABC en Mexicali</title>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: #eef1f4; }
  #toast { display: none; position: fixed; top: 12px; left: 50%; transform: translateX(-50%); color: #fff; padding: 13px 22px; border-radius: 14px; font-size: 14.5px; z-index: 99; box-shadow: 0 4px 16px rgba(0,0,0,.35); max-width: 92%; text-align: center; }
  .wrap { max-width: 1200px; margin: 0 auto; height: 100vh; display: flex; flex-direction: row; }
  #side { width: 260px; background: #004d38; color: #fff; padding: 14px 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
  #side b { font-size: 14px; }
  #side button { background: rgba(255,255,255,.12); color: #fff; border: none; border-radius: 10px; padding: 9px 10px; text-align: left; cursor: pointer; font-size: 12.5px; }
  #side button:hover { background: rgba(255,255,255,.25); }
  main { flex: 1; display: flex; flex-direction: column; height: 100vh; }
  header { background: linear-gradient(135deg, #00684a, #00855f); color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; border-radius: 0 0 18px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.15); }
  header img { width: 54px; height: 54px; background: #fff; border-radius: 12px; padding: 3px; }
  header h1 { font-size: 17px; } header p { font-size: 12px; opacity: .85; }
  .langs { display: flex; gap: 5px; margin-left: 14px; }
  .langs button { font-size: 11px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: transparent; color: #fff; cursor: pointer; }
  .langs button.on { background: #f7941d; border-color: #f7941d; font-weight: 700; }
  .hbtn { background: rgba(255,255,255,.15); border: none; border-radius: 999px; width: 36px; height: 36px; cursor: pointer; font-size: 16px; }
  #nuevo { margin-left: auto; }
  #chat { flex: 1; overflow-y: auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 82%; display: flex; flex-direction: column; gap: 4px; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.bot { align-self: flex-start; align-items: flex-start; }
  .bub { padding: 10px 14px; border-radius: 16px; font-size: 14.5px; line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,.12); white-space: pre-wrap; }
  .user .bub { background: #d9f6c8; border-bottom-right-radius: 4px; }
  .bot .bub { background: #fff; border-bottom-left-radius: 4px; }
  .msg audio { width: 260px; max-width: 100%; }
  .think .bub { background: #fff; color: #666; font-style: italic; }
  .dots::after { content: ''; animation: pts 1.2s steps(4) infinite; }
  @keyframes pts { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75% { content: '...'; } }
  .opts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .opts button { font-size: 12.5px; padding: 7px 11px; border-radius: 999px; border: 1px solid #00855f; background: #f2fbf6; color: #00684a; cursor: pointer; }
  .opts button:hover { background: #00855f; color: #fff; }
  .nota { display: block; margin-top: 9px; font-size: 12px; color: #888; }
  .bar { display: flex; gap: 8px; padding: 10px 12px 14px; align-items: center; }
  #mic { width: 46px; height: 46px; border-radius: 50%; border: none; background: #00684a; color: #fff; font-size: 19px; cursor: pointer; flex-shrink: 0; }
  #mic.rec { background: #d32f2f; animation: pulso 1s infinite; }
  @keyframes pulso { 50% { transform: scale(1.12); } }
  #inp { flex: 1; border: 1px solid #cfd8dc; border-radius: 999px; padding: 12px 18px; font-size: 15px; outline: none; }
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
    .bub { font-size: 16.5px; }
    header h1 { font-size: 21px; }
    header p { font-size: 13px; }
    #inp { font-size: 17px; padding: 14px 22px; }
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
      <div><h1>UABCBot Idiomas</h1><p id="hsub">Facultad de Idiomas de la UABC en Mexicali</p></div>
      <div class="langs">
        <button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button>
      </div>
      <button id="convs" class="hbtn" title="Conversaciones">🗂️</button>
      <button id="user" class="hbtn" title="Tu cuenta">👤</button>
      <button id="nuevo" class="hbtn" title="Nueva conversación">🧹</button>
    </header>
    <button id="gear" title="Personal autorizado">⚙️</button>
    <div id="cdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button><b>🗂️ Conversaciones</b><div id="lista2"></div></div>
    <div id="udrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>👤 Tu cuenta</b>
      <div id="who"></div>
      <input id="uusr" placeholder="Usuario o correo">
      <input id="ukey" type="password" placeholder="Clave">
      <button id="ureg">✨ Registrarme</button>
      <button id="ulin">🔑 Entrar</button>
      <button id="uguest">👋 Seguir como invitado</button>
      <button id="uout">🚪 Cerrar sesión</button>
    </div>
    <div id="chat"></div>
    <div id="fbdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>🚩 Reportar respuesta no resuelta</b>
      <span class="etiq">Área responsable</span>
      <select id="fbarea">
        <option>Admisión</option><option>CEC</option><option>Escolar/Escolaridad</option><option>Egresados/Bolsa de trabajo</option><option>Eventos</option><option>Otro</option>
      </select>
      <span class="etiq">Cuéntanos qué faltó</span>
      <textarea id="fbcom" rows="3" placeholder="Ej. No me dijo la fecha exacta del examen de admisión…"></textarea>
      <div id="fbprev" class="fb-captura">📸 Se adjuntará una captura de pantalla automática del chat.</div>
      <button id="fbsend">📨 Enviar al responsable</button>
    </div>
    <div id="drawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>🛠️ Panel de personal</b>
      <input id="clave" type="password" placeholder="Clave de acceso (Enter para entrar)">
      <button id="unlock">🔓 Entrar</button>
      <button id="salirp">🚪 Salir del panel</button>
      <div id="zona" style="display:none">
        <span class="etiq">1️⃣ Categoría del aviso</span>
        <select id="fcat">
          <option>Avisos</option><option>Eventos</option><option>Suspensiones</option><option>Horarios</option><option>Exámenes</option><option>Convocatorias</option><option>TSU</option><option>PlanDeEstudios</option>
        </select>
        <span class="etiq">2️⃣ Vigente hasta (opcional)</span>
        <input id="fvig" type="date">
        <span class="etiq">3️⃣ Elige o arrastra el archivo (TXT, PDF o imagen)</span>
        <div id="drop">📥 Arrastra aquí tu documento o póster<br><small>o toca para elegirlo</small></div>
        <input id="ffile" type="file" style="display:none">
        <span class="etiq">📝 Texto del póster (plan B recomendado para imágenes)</span>
        <div class="ayuda">Si subes una IMAGEN y el motor de visión está saturado, copia y pega aquí lo que dice el póster (evento, fecha, hora, lugar) y se publicará al instante sin esperar.</div>
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
let hist = [], state = {pending:false, active:false}, langPref = "auto", rec = null, rec2 = null, chunks = [], currentId = uid(), droppedFile = null, thinkTimer = null, thinkSec = 0, toastTimer = null, lastPregunta = "", lastRespuesta = "", capturaPendiente = "";
let currentUser = localStorage.getItem('uabc_user') || "";
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
  es: 'Personal docente: escribe o di "administración". Si una respuesta no te resuelve, toca 🚩.',
  en: 'Faculty staff: type or say "administración". If an answer doesn’t help you, tap 🚩.',
  fr: 'Personnel : écris ou dis « administración ». Si une réponse ne t’aide pas, touche 🚩.'
};
const UI = {
  es: {sub: "Facultad de Idiomas de la UABC en Mexicali", side: "🗂️ Conversaciones", new: "➕ Nueva conversación", ph: "Escribe o dime tu pregunta…"},
  en: {sub: "Faculty of Languages of UABC in Mexicali", side: "🗂️ Conversations", new: "➕ New conversation", ph: "Type or say your question…"},
  fr: {sub: "Faculté de Langues de l’UABC à Mexicali", side: "🗂️ Conversations", new: "➕ Nouvelle conversation", ph: "Écris ou dis ta question…"}
};
function uid(){ return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2,7); }
function langUI(){ return (langPref in BIENVENIDAS) ? langPref : 'es'; }
function applyLang(L){
  const u = UI[L] || UI.es;
  document.getElementById('hsub').innerText = u.sub;
  document.getElementById('sidet').innerText = u.side;
  document.getElementById('sidenew').innerText = u.new;
  document.getElementById('inp').placeholder = u.ph;
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
  let opts = [
    {q:"¿Cuántos créditos necesito para titularme en Traducción?", t:"💳 Créditos para titularme"},
    {q:"¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?", t:"📅 Horarios del CEC"},
    {q:"¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?", t:"🎓 Requisitos de admisión"},
    {q:"¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?", t:"🏛️ Carreras y TSU"}
  ];
  try {
    const d = await (await fetch('/api/topfaq')).json();
    if (d && d.length) opts = d.map(x => ({q: x.q, t: "🔥 " + (x.q.length > 40 ? x.q.slice(0,40) + "…" : x.q)}));
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
  document.getElementById('who').innerText = currentUser ? '✅ Sesión: ' + currentUser + ' (tus conversaciones se guardan)' : '👋 Modo invitado: sin memoria de conversaciones.';
}
function saveConv(){
  if (!currentUser) return;
  const titulo = ((hist.find(m => m.role === 'user') || {}).content || 'Nueva conversación').slice(0, 40);
  fetch('/api/conv/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: currentId, user: currentUser, titulo, msgs: hist})}).then(() => loadList());
}
async function loadList(){
  if (!currentUser) {
    const msg = '<small>👋 Invitado: sin memoria. Regístrate con 👤 para guardar tus conversaciones.</small>';
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
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg, hist: hist.slice(-7), state, lang: langPref})});
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
document.getElementById('fb').onclick = async () => {
  if (!lastRespuesta) { avisar('⚠️ Aún no hay respuestas que reportar.', 'error'); return; }
  // 📸 Captura automática del chat
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
  avisar('⏳ Enviando reporte con captura...', 'warn');
  const r = await fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
    pregunta: lastPregunta, respuesta: lastRespuesta,
    comentario: document.getElementById('fbcom').value,
    area: document.getElementById('fbarea').value,
    captura: capturaPendiente
  })});
  const d = await r.json();
  document.getElementById('fbcom').value = '';
  document.getElementById('fbdrawer').style.display = 'none';
  capturaPendiente = "";
  avisar('📨 Reporte y captura enviados al responsable. ¡Gracias por ayudar a mejorar el bot!', 'ok');
};
document.getElementById('ureg').onclick = async () => {
  const d = await (await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('✅ Bienvenido, ' + currentUser + '. Tus conversaciones se guardarán.', 'ok');
};
document.getElementById('ulin').onclick = async () => {
  const d = await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('✅ Sesión iniciada: ' + currentUser, 'ok');
};
document.getElementById('uguest').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; };
document.getElementById('uout').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; avisar('👋 Sesión cerrada.'); };
[['Lauto','auto'],['Les','es'],['Len','en'],['Lfr','fr']].forEach(([id, v]) => {
  document.getElementById(id).onclick = e => {
    langPref = v;
    document.querySelectorAll('.langs button').forEach(x => x.classList.remove('on'));
    e.target.classList.add('on');
    applyLang(langUI());
    if (!hist.length) { chat.innerHTML = ''; welcome(); }
    else avisar(v === 'auto' ? ' AUTO: español por defecto; si te leo o escucho en otro idioma, todo cambia a ese idioma.' : '🌐 Interfaz y respuestas en ' + v.toUpperCase());
  };
});
const drop = document.getElementById('drop');
function marcarArchivo(f){
  droppedFile = f;
  drop.innerHTML = '📎 ' + esc(f.name);
  avisar('📎 Archivo listo: ' + f.name + ' → pulsa "📤 Subir y publicar".');
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
    const d = await (await fetch('/api/voice', {method:'POST', body: fd})).json();
    removeThink(); state = d.state;
    if (langPref === 'auto' && d.lang) applyLang(d.lang);
    if (d.texto) { bubble('user', '🎤 ' + d.texto); hist.push({role:'user', content: d.texto}); lastPregunta = d.texto; }
    if (d.reply) { bubble('bot', d.reply, d.audio); hist.push({role:'assistant', content: d.reply, audio: d.audio}); lastRespuesta = d.reply; }
    saveConv();
  };
  rec.start(); mic.classList.add('rec');
  avisar('🎤 Grabando tu pregunta… toca el micrófono para terminar. Te escucho en español, inglés o francés.');
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
  else avisar('❌ Clave incorrecta.', 'error');
};
document.getElementById('fsubir').onclick = async () => {
  const f = document.getElementById('ffile').files[0] || droppedFile;
  if (!f && !document.getElementById('ftexto').value.trim()) { avisar('⚠️ Elige un archivo o pega el texto del aviso en el cuadro 📝.', 'error'); return; }
  avisar('⏳ Procesando y publicando… puede tardar unos segundos.');
  const fd = new FormData();
  if (f) fd.append('archivo', f);
  fd.append('categoria', document.getElementById('fcat').value);
  fd.append('vigencia', document.getElementById('fvig').value);
  fd.append('reemplazar', '0');
  fd.append('texto_manual', document.getElementById('ftexto').value);
  const d = await (await fetch('/api/upload', {method:'POST', body: fd})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.startsWith('✅') ? 'ok' : 'error');
  loadDocs();
};
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
    avisar('⏳ Transcribiendo y publicando tu nota…');
    const fd = new FormData();
    fd.append('audio', new Blob(ch, {type:'audio/webm'}), 'nota.webm');
    fd.append('categoria', document.getElementById('fcat').value);
    const d = await (await fetch('/api/voice_note', {method:'POST', body: fd})).json();
    document.getElementById('fest').innerText = d.estado;
    avisar(d.estado, d.estado.startsWith('✅') ? 'ok' : 'error');
    loadDocs();
  };
  rec2.start();
  avisar('🔴 Grabando nota… toca de nuevo para terminar y publicar.');
};
document.getElementById('rep').onclick = async () => {
  const d = await (await fetch('/api/report', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})})).json();
  if (d.error) { avisar(d.error, 'error'); return; }
  document.getElementById('fest').innerText = '📊 Total: ' + d.total + ' · Hoy: ' + d.hoy + ' · Idiomas: ' + JSON.stringify(d.idiomas)
    + '\\n\\n🔥 Más frecuentes:\\n' + d.top.map((x, i) => (i+1) + '. ' + x[0] + ' (' + x[1] + ')').join('\\n');
  avisar('📊 Reporte listo en el panel.', 'ok');
};
welcome(); loadList(); refreshWho(); inp.focus();
</script>
</body>
</html>
"""

@app.get("/")
async def inicio():
    return HTMLResponse(PAGINA)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
