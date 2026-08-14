import os
import re
import asyncio
import tempfile
import requests
from google.genai import types

try:
    from config import client as cliente_gemini
except Exception:
    cliente_gemini = None

BASE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(BASE, "Manual_Aspirantes_Idiomas_UABC.txt")
CARPETA = os.path.join(BASE, "datos_bot")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")

VOCES = {"es": "es-MX-DaliaNeural", "en": "en-US-AriaNeural", "fr": "fr-FR-DeniseNeural"}

def detectar_idioma(texto):
    t = (texto or "").lower()
    fr = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplôme", "traduction", "salut", "crédits"]
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
            partes.append(f.read())
    except Exception:
        pass
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                try:
                    with open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore") as f:
                        partes.append(f.read())
                except Exception:
                    pass
    return "\n\n".join(partes)[:18000]

def sistema_prompt(contexto):
    return (
        "Eres UABCBot Idiomas, asistente virtual de la Facultad de Idiomas de la UABC (Mexicali). "
        "Responde con amabilidad y en el idioma de la pregunta (español, inglés o francés), usando SOLO el CONTEXTO. "
        "No inventes datos. No escripas etiquetas ni corchetes al inicio de la respuesta. "
        "Si la información no está en el CONTEXTO, sugiere contactar a la Facultad: tel. 686-689-0825, idiomas.mxl@uabc.edu.mx, idiomas.mxl.uabc.mx. "
        f"\n=== CONTEXTO ===\n{contexto}"
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
            config=types.GenerateContentConfig(system_instruction=sp),
        )
        return (r.text or "").strip() or None
    except Exception:
        return None

def llamar_openai(sp, hist, pregunta, url, key, modelo):
    if not key:
        return None
    try:
        msgs = [{"role": "system", "content": sp}] + hist + [{"role": "user", "content": pregunta}]
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": modelo, "messages": msgs},
            timeout=60,
        )
        d = r.json()
        return (d["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None

def responder(pregunta, historial):
    contexto = cargar_contexto()
    sp = sistema_prompt(contexto)
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    texto = llamar_gemini(sp, hist, pregunta)
    if not texto:
        texto = llamar_openai(sp, hist, pregunta, "https://api.groq.com/openai/v1/chat/completions", GROQ_KEY, "llama-3.3-70b-versatile")
    if not texto:
        texto = llamar_openai(sp, hist, pregunta, "https://openrouter.ai/api/v1/chat/completions", OR_KEY, "meta-llama/llama-3.3-70b-instruct:free")
    if not texto:
        texto = "⚠️ No pude generar una respuesta en este momento. Intenta de nuevo en unos segundos."
    texto = re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto).strip()
    return texto, detectar_idioma(pregunta)

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
