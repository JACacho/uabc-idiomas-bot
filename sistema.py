import os
import re
import json
import time
import asyncio
import tempfile
import requests
from datetime import datetime
from google.genai import types

try:
    from config import client as cliente_gemini
except Exception:
    cliente_gemini = None

BASE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(BASE, "Manual_Aspirantes_Idiomas_UABC.txt")
CARPETA = os.path.join(BASE, "datos_bot")
CACHE = os.path.join(BASE, "cache.json")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")

VOCES = {"es": "es-MX-DaliaNeural", "en": "en-US-AriaNeural", "fr": "fr-FR-DeniseNeural"}

def detectar_idioma(texto):
    t = (texto or "").lower()
    fr = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplôme", "traduction", "salut", "crédits", "je", "étudier", "français"]
    en = ["hello", "thank", "how many", "credits", "degree", "translation", "what", "when", "where", "i want"]
    hf = sum(1 for w in fr if w in t)
    he = sum(1 for w in en if w in t)
    if hf >= 2 and hf > he:
        return "fr"
    if he >= 2 and he > hf:
        return "en"
    return "es"

def cargar_contexto():
    partes = []
    try:
        with open(MANUAL, encoding="utf-8", errors="ignore") as f:
            partes.append("MANUAL OFICIAL:\n" + f.read())
    except Exception:
        pass
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                try:
                    with open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore") as f:
                        partes.append("DOCUMENTO " + fn + ":\n" + f.read())
                except Exception:
                    pass
    return "\n\n".join(partes)[:18000]

def sistema_prompt(contexto):
    hoy = datetime.now().strftime("%A %d de %B de %Y")
    return (
        f"Hoy es {hoy}. Eres UABCBot Idiomas, asistente virtual de la Facultad de Idiomas de la UABC en Mexicali. "
        "Responde con amabilidad y en el idioma de la pregunta (español, inglés o francés), usando el CONTEXTO. "
        "Si la respuesta está en el CONTEXTO, úsala con sus datos exactos (cifras, fechas, teléfonos). "
        "No inventes datos ni repitas encabezados técnicos del CONTEXTO. No escribas etiquetas ni corchetes al inicio. "
        "Solo si la información realmente NO aparece en el CONTEXTO, sugiere contactar a la Facultad: tel. 686-689-0825, idiomas.mxl@uabc.edu.mx, idiomas.mxl.uabc.mx. "
        f"\n=== CONTEXTO ===\n{contexto}"
    )

def llamar_gemini(sp, hist, pregunta):
    if not cliente_gemini:
        return None
    for intento in (1, 2):
        try:
            contents = []
            for m in hist:
                contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
            contents.append({"role": "user", "parts": [{"text": pregunta}]})
            r = cliente_gemini.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=sp, temperature=0.2),
            )
            t = (r.text or "").strip()
            if t:
                return t
        except Exception:
            if intento == 1:
                time.sleep(1)
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
                json={"model": modelo, "messages": msgs, "temperature": 0.2},
                timeout=30,
            )
            d = r.json()
            t = (d["choices"][0]["message"]["content"] or "").strip()
            if t:
                return t
        except Exception:
            continue
    return None

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
    return not (texto.startswith("⚠️") or "no está en el contexto" in t or "===" in texto or "manual de conocimiento" in t)

def responder(pregunta, historial):
    clave = (pregunta or "").strip().lower()[:120]
    cache = _cargar_cache()
    if clave in cache:
        return cache[clave][0], cache[clave][1]
    contexto = cargar_contexto()
    sp = sistema_prompt(contexto)
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    texto = llamar_gemini(sp, hist, pregunta)
    if not texto:
        texto = llamar_openai(sp, hist, pregunta, "https://api.groq.com/openai/v1/chat/completions", GROQ_KEY, ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"])
    if not texto:
        texto = llamar_openai(sp, hist, pregunta, "https://openrouter.ai/api/v1/chat/completions", OR_KEY, ["meta-llama/llama-3.3-70b-instruct:free", "google/gemma-3-27b-it:free", "mistralai/mistral-7b-instruct:free"])
    if not texto:
        texto = "⚠️ Los motores de IA están saturados en este momento. Intenta de nuevo en unos segundos."
    texto = re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto).strip()
    lang = detectar_idioma(pregunta)
    if _es_cacheable(texto):
        cache[clave] = [texto, lang]
        _guardar_cache(cache)
    return texto, lang

def transcribir_groq(data):
    if not GROQ_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("voz.webm", data, "audio/webm")},
            data={"model": "whisper-large-v3"},
            timeout=60,
        )
        return (r.json().get("text") or "").strip()
    except Exception:
        return ""

def transcribir(audio_bytes):
    if cliente_gemini:
        for modelo in ("gemini-2.5-flash", "gemini-2.0-flash"):
            for mime in ("audio/webm", "audio/wav", "audio/mp3", "audio/ogg"):
                try:
                    r = cliente_gemini.models.generate_content(
                        model=modelo,
                        contents=[
                            types.Part(inline_data=types.Blob(data=audio_bytes, mime_type=mime)),
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

def extraer_imagen(data, mime="image/jpeg"):
    if not cliente_gemini:
        return ""
    for modelo in ("gemini-2.5-flash", "gemini-2.0-flash"):
        try:
            r = cliente_gemini.models.generate_content(
                model=modelo,
                contents=[
                    types.Part(inline_data=types.Blob(data=data, mime_type=mime)),
                    "Este es un anuncio o póster institucional. Extrae TODA la información útil (qué evento, quién invita, fecha, hora, lugar, contacto, requisitos) y devuélvela como texto claro en español, sin comentarios.",
                ],
            )
            t = (r.text or "").strip()
            if t:
                return t
        except Exception:
            continue
    return ""

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
