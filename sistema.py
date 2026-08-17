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

MEMORIA_OFICIAL = [
    (["credito", "titular"],
     "Para titularte en la Licenciatura en Traducción (LT) de la Facultad de Idiomas de la UABC necesitas un total de 349 créditos: 237 de materias obligatorias, 102 de materias optativas y 10 de prácticas profesionales. Para más detalles consulta idiomas.mxl.uabc.mx o llama al 686-689-0825."),
    (["horario", "cec"],
     "El Centro de Enseñanza de Lenguas (CEC) ofrece cursos en formatos semanal, sabatino, intensivo e intersemestral, con horarios matutinos, vespertinos y nocturnos. Los grupos exactos de cada periodo se publican en la convocatoria vigente en cecuabc.com y lenguasextranjeras.uabc.mx. Informes: recepcionmxl@uabc.edu.mx o al 686 841-82-91 ext. 300."),
    (["admision", "requisito"],
     "Para ingresar a la Facultad de Idiomas necesitas: 1) concluir el bachillerato con promedio aprobatorio, 2) certificado de bachillerato, acta de nacimiento y CURP, 3) registrarte en el portal de admisiones cuando abra la convocatoria (dos veces al año: en agosto y en enero), y 4) presentar el Examen de Selección institucional. No se requiere inglés avanzado: la Facultad te forma desde cero hasta nivel profesional. Fechas exactas en admision.uabc.mx."),
    (["carrera", "tsu", "tecnico"],
     "La Facultad de Idiomas ofrece dos licenciaturas: Enseñanza de Lenguas (LEL) y Traducción (LT), además del Técnico Superior Universitario (TSU), una opción de nivel superior con enfoque práctico y rápida salida al campo laboral. Consulta la convocatoria vigente en idiomas.mxl.uabc.mx o llama al 686-689-0825 para confirmar la especialidad del ciclo actual."),
]

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

def cargar_contexto(pregunta):
    partes = []
    try:
        with open(MANUAL, encoding="utf-8", errors="ignore") as f:
            partes.append(_limpiar_doc(f.read()))
    except Exception:
        pass
    qt = _tokens(pregunta)
    docs = []
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                try:
                    with open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore") as f:
                        texto = _limpiar_doc(f.read())
                except Exception:
                    continue
                score = len(qt & _tokens(texto))
                docs.append((score, texto))
    docs.sort(key=lambda x: x[0], reverse=True)
    for score, texto in docs[:3]:
        if score >= 1:
            partes.append(texto)
    return "\n\n".join(partes)[:12000]

def sistema_prompt(contexto):
    hoy = datetime.now().strftime("%A %d de %B de %Y")
    return (
        f"Hoy es {hoy}. Eres UABCBot Idiomas, asistente virtual de la Facultad de Idiomas de la UABC en Mexicali. "
        "Responde con amabilidad, en el idioma de la pregunta (español, inglés o francés), y en párrafos naturales. "
        "REGLAS DE ORO: reformula la información con tus propias palabras; NUNCA copies ni menciones nombres de archivo, "
        "encabezados con ===, ni palabras como DOCUMENTO o CONTEXTO; usa solo los datos disponibles (cifras, fechas, teléfonos). "
        "Si la información no aparece, sugiere contactar a la Facultad: tel. 686-689-0825, idiomas.mxl@uabc.edu.mx, idiomas.mxl.uabc.mx. "
        f"\nINFORMACIÓN DISPONIBLE:\n{contexto}"
    )

def llamar_gemini(sp, hist, pregunta):
    if not cliente_gemini:
        return None
    try:
        contents = []
        for m in hist:
            contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": pregunta}]})
        r = cliente_gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=sp, temperature=0.1),
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
                timeout=20,
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
    return not (texto.startswith("⚠️") or "no está en el contexto" in t or "===" in texto or "documento " in t or "manual de conocimiento" in t)

def responder(pregunta, historial):
    p = (pregunta or "").lower()
    for claves, respuesta_oficial in MEMORIA_OFICIAL:
        if any(k in p for k in claves):
            return respuesta_oficial, detectar_idioma(pregunta)
    clave = p.strip()[:120]
    cache = _cargar_cache()
    if clave in cache:
        return cache[clave][0], cache[clave][1]
    contexto = cargar_contexto(pregunta)
    sp = sistema_prompt(contexto)
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    texto = llamar_gemini(sp, hist, pregunta)
    if not texto:
        texto = llamar_openai(sp, hist, pregunta, "https://api.groq.com/openai/v1/chat/completions", GROQ_KEY, ["llama-3.3-70b-versatile"])
    if not texto:
        texto = llamar_openai(sp, hist, pregunta, "https://openrouter.ai/api/v1/chat/completions", OR_KEY, ["meta-llama/llama-3.3-70b-instruct:free"])
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
