import os
import re
import asyncio
import base64
import requests
import gradio as gr
from datetime import datetime
from sistema import responder, transcribir, generar_voz
from config import client as cliente_gemini
from google.genai import types

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE, "datos_bot")
CONTADOR = os.path.join(BASE, "conteo.txt")
CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "fimxl2026")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPO", "")
MEMORIA = 6
LOGO = os.path.join(BASE, "logo.png")
LOGO_URL = "https://codeberg.org/uabc-bot/uabc-idiomas-bot/raw/main/logo.png"

CSS = """
.gradio-container { max-width: 720px !important; }
footer { display: none !important; }
.gr-row { align-items: center !important; }
#chat-wa { background: #ece5dd; border-radius: 14px; padding: 8px; }
"""

BIENVENIDA = [{"role": "assistant", "content": "👋 ¡Hola! Soy *UABCBot Idiomas*, el asistente de la Facultad de Idiomas UABC. Toca una opción abajo o escribe/dime tu pregunta en español, inglés o francés. (Personal docente: escribe o di *administración*)."}]

try:
    if not os.path.exists(LOGO):
        r = requests.get(LOGO_URL, timeout=10)
        if r.status_code == 200 and r.content:
            with open(LOGO, "wb") as f:
                f.write(r.content)
except Exception:
    pass

def limpiar_tags(texto):
    return re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto or "").strip()

def github_subir(ruta_repo, contenido_bytes):
    if not GH_TOKEN or not GH_REPO:
        return "⚠️ Vivo solo en esta sesión (falta token de GitHub)."
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

def sumar_pregunta():
    try:
        n = 0
        if os.path.exists(CONTADOR):
            n = int(open(CONTADOR).read().strip() or "0")
        n += 1
        with open(CONTADOR, "w") as f:
            f.write(str(n))
    except Exception:
        pass

def leer_contador():
    try:
        return open(CONTADOR).read().strip() or "0"
    except Exception:
        return "0"

def guardar_aviso(texto, categoria="Avisos"):
    os.makedirs(CARPETA, exist_ok=True)
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: sin límite ===\n"
    contenido = cab + texto
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(contenido)
    return nuevo, github_subir(f"datos_bot/{nuevo}", contenido.encode("utf-8"))

def transcribir_voz(data):
    if cliente_gemini:
        for modelo in ("gemini-2.5-flash", "gemini-2.0-flash"):
            for mime in ("audio/webm", "audio/wav", "audio/mp3", "audio/ogg"):
                try:
                    r = cliente_gemini.models.generate_content(
                        model=modelo,
                        contents=[
                            types.Part(inline_data=types.Blob(data=data, mime_type=mime)),
                            "Transcribe textualmente lo que se dice en este audio. El idioma puede ser español, inglés o francés. Devuelve únicamente la transcripción, sin comentarios.",
                        ],
                    )
                    texto = (r.text or "").strip()
                    if texto:
                        return texto
                except Exception:
                    continue
    texto, _ = transcribir(data)
    return texto

def construir_historial(historial):
    msgs = []
    for m in historial[-MEMORIA:]:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            msgs.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    return msgs

def decir(historial, pregunta, respuesta):
    ruta_voz = asyncio.run(generar_voz(respuesta, "es"))
    if pregunta:
        historial.append({"role": "user", "content": pregunta})
    historial.append({"role": "assistant", "content": respuesta})
    return historial, ruta_voz

def router(pregunta, historial, state):
    historial = historial or []
    state = state or {"pending": False, "active": False}
    texto = (pregunta or "").strip()
    if not texto:
        return historial, None, state
    if state.get("pending"):
        state["pending"] = False
        if texto == CLAVE_ADMIN:
            state["active"] = True
            return decir(historial, "••••••", "✅ Acceso concedido, profe. Escribe tu aviso tal cual (ej. 'AVISO: se suspenden clases el viernes por calor') y lo publico al instante. Escribe SALIR para cerrar.") + (state,)
        return decir(historial, "••••••", "❌ Clave incorrecta.") + (state,)
    if state.get("active"):
        if texto.upper() == "SALIR":
            state["active"] = False
            return decir(historial, texto, "🔒 Sesión de administración cerrada. Vuelvo a modo aspirante.") + (state,)
        nuevo, resp = guardar_aviso(texto)
        return decir(historial, texto, f"✅ Publicado y aprendido al instante. {resp} Los alumnos ya pueden preguntármelo.") + (state,)
    if "administraci" in texto.lower():
        state["pending"] = True
        return decir(historial, texto, "🔐 Para entrar al modo de administración, escribe la clave de acceso.") + (state,)
    sumar_pregunta()
    contexto = construir_historial(historial)
    try:
        respuesta, lang = responder(texto, contexto)
    except Exception:
        respuesta, lang = responder(texto, [])
    respuesta = limpiar_tags(respuesta)
    ruta_voz = asyncio.run(generar_voz(respuesta, lang))
    historial.append({"role": "user", "content": texto})
    historial.append({"role": "assistant", "content": respuesta})
    return
