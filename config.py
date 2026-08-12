import os
import requests
import streamlit as st
from google import genai
from google.genai import types

# ============ CLAVES (¡PEGA AQUÍ LAS DOS!) ============
GEMINI_API_KEY = "PEGA_AQUI..."
GROQ_API_KEY = ""
OPENROUTER_API_KEY = "PEGA_AQUI..."

TRUSTED = ["uabc.mx", "gob.mx", "sep.gob.mx", "cecuabc.com", "facebook.com/EducacionContinuaUABC"]

MODELOS_GEMINI = ["gemini-3-flash", "gemini-3-flash-preview", "gemini-3-pro",
                  "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"]
MODELOS_GROQ = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
MODELOS_OR = ["meta-llama/llama-3.1-8b-instruct:free", "mistralai/mistral-7b-instruct:free"]

VOCES = {"es": "es-MX-DaliaNeural", "en": "en-US-AriaNeural",
         "fr": "fr-FR-DeniseNeural", "pt": "pt-BR-FranciscaNeural"}

def _key(nombre, valor_local):
    try:
        return st.secrets[nombre]
    except Exception:
        return os.environ.get(nombre, valor_local)

gemini_key = _key("GEMINI_API_KEY", GEMINI_API_KEY)
groq_key = _key("GROQ_API_KEY", GROQ_API_KEY)
or_key = _key("OPENROUTER_API_KEY", OPENROUTER_API_KEY)

client = genai.Client(api_key=gemini_key) if gemini_key else None

class Respuesta:
    def __init__(self, text):
        self.text = text

def _es_multimodal(contents):
    for c in contents:
        for p in c.get("parts", []):
            if not (isinstance(p, dict) and "text" in p):
                return True
    return False

def _a_texto(contents):
    msgs = []
    for c in contents:
        rol = "user" if c.get("role") == "user" else "assistant"
        textos = [p["text"] for p in c.get("parts", []) if isinstance(p, dict) and "text" in p]
        if textos:
            msgs.append({"role": rol, "content": "\n".join(textos)})
    return msgs

def _llamar_http(url, clave, modelo, contents, instruccion):
    msgs = _a_texto(contents)
    if instruccion:
        msgs = [{"role": "system", "content": instruccion}] + msgs
    resp = requests.post(url, headers={"Authorization": f"Bearer {clave}"},
                         json={"model": modelo, "messages": msgs}, timeout=90)
    resp.raise_for_status()
    return Respuesta(resp.json()["choices"][0]["message"]["content"])

def _modelos_free_openrouter():
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        r.raise_for_status()
        libres = [m["id"] for m in r.json().get("data", [])
                  if str(m.get("id", "")).endswith(":free")]
        return (libres[:3] + MODELOS_OR) if libres else MODELOS_OR
    except Exception:
        return MODELOS_OR

def generar(contents, instruccion=None):
    errores = []
    if client:
        for m in MODELOS_GEMINI:
            try:
                config = types.GenerateContentConfig(system_instruction=instruccion) if instruccion else None
                r = client.models.generate_content(model=m, contents=contents, config=config)
                return Respuesta(r.text)
            except Exception as e:
                errores.append(f"Gemini/{m}: {str(e)[:60]}")
    if groq_key and not _es_multimodal(contents):
        for m in MODELOS_GROQ:
            try:
                return _llamar_http("https://api.groq.com/openai/v1/chat/completions",
                                    groq_key, m, contents, instruccion)
            except Exception as e:
                errores.append(f"Groq/{m}: {str(e)[:60]}")
    if or_key and not _es_multimodal(contents):
        for m in _modelos_free_openrouter():
            try:
                return _llamar_http("https://openrouter.ai/api/v1/chat/completions",
                                    or_key, m, contents, instruccion)
            except Exception as e:
                errores.append(f"OpenRouter/{m}: {str(e)[:60]}")
    raise Exception("Fallaron todas las IAs: " + " | ".join(errores[-4:]))

def busqueda_web(pregunta):
    resultados = []
    from duckduckgo_search import DDGS
    with DDGS() as d:
        for r in d.text(pregunta, max_results=15):
            if any(s in r["href"] for s in TRUSTED):
                resultados.append(f"- {r['title']}: {r['body']} (Fuente: {r['href']})")
    return "\n".join(resultados[:4]) or "Sin resultados oficiales."