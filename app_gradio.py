import os
import re
import asyncio
import base64
import requests
import gradio as gr
from datetime import datetime
from sistema import responder, transcribir, generar_voz

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
.gradio-container { max-width: 760px !important; }
footer { display: none !important; }
.gr-row { align-items: center !important; }
#chat-wa { background: #e9e0d7; border-radius: 18px; padding: 10px; box-shadow: inset 0 1px 4px rgba(0,0,0,.08); }
#inputbar { border-radius: 22px !important; box-shadow: 0 2px 10px rgba(0,0,0,.10); }
#inputbar .textbox { border-radius: 999px !important; }
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
    return historial, ruta_voz, state

def procesar_voz(audio_path, historial, state):
    if not audio_path:
        return historial, None, state
    with open(audio_path, "rb") as f:
        data = f.read()
    texto, _ = transcribir(data)
    if not texto:
        return historial, None, state
    return router(texto, historial, state)

def rapida(texto):
    def fn(hist, state):
        return router(texto, hist, state)
    return fn

def limpiar_chat():
    return [], None, {"pending": False, "active": False}

def extraer_texto(ruta, nombre):
    if nombre.lower().endswith(".pdf"):
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        return "\n".join((p.extract_text() or "") for p in lector.pages)
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        return f.read()

def subir_doc(archivo, categoria, vigencia, reemplazar):
    if archivo is None:
        return "⚠️ Selecciona un archivo primero."
    os.makedirs(CARPETA, exist_ok=True)
    nombre = os.path.basename(archivo)
    texto = extraer_texto(archivo, nombre)
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia or 'sin límite'} ===\n"
    contenido = cab + texto
    if reemplazar:
        for fn in list(os.listdir(CARPETA)):
            if fn.endswith(f"_{categoria}.txt"):
                os.remove(os.path.join(CARPETA, fn))
                github_borrar(f"datos_bot/{fn}")
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(contenido)
    resp = github_subir(f"datos_bot/{nuevo}", contenido.encode("utf-8"))
    return f"✅ Guardado como {nuevo}. {resp}"

def listar_docs():
    if not os.path.isdir(CARPETA):
        return "Aún no hay documentos adicionales."
    archivos = [f for f in sorted(os.listdir(CARPETA)) if f.endswith(".txt")]
    return "\n".join(archivos) or "Aún no hay documentos adicionales."

def borrar_doc(nombre):
    ruta = os.path.join(CARPETA, nombre.strip())
    if os.path.exists(ruta):
        os.remove(ruta)
        github_borrar(f"datos_bot/{nombre.strip()}")
        return f"🗑️ {nombre} eliminado (también del respaldo)."
    return "No encontrado."

with gr.Blocks(title="UABCBot Idiomas UABC") as demo:
    estado_admin = gr.State({"pending": False, "active": False})
    if os.path.exists(LOGO):
        with gr.Row():
            gr.Image(value=LOGO, width=110, interactive=False, show_label=False, scale=1)
            gr.Markdown("### 🎓 UABCBot Idiomas — Facultad de Idiomas UABC\nAsistente oficial trilingüe (español · inglés · francés).", scale=5)
    else:
        gr.Markdown("### 🎓 UABCBot Idiomas — Facultad de Idiomas UABC")
    try:
        chatbot = gr.Chatbot(value=BIENVENIDA, height=480, elem_id="chat-wa", type="messages")
    except TypeError:
        chatbot = gr.Chatbot(value=BIENVENIDA, height=480, elem_id="chat-wa")
    audio_out = gr.Audio(label="🔊 Nota de voz de la respuesta (toca play aquí)", type="filepath")
    with gr.Row():
        q1 = gr.Button("💳 Créditos para titularme", size="sm")
        q2 = gr.Button("📅 Horarios del CEC", size="sm")
        q3 = gr.Button("🎓 Requisitos de admisión", size="sm")
    with gr.Row():
        q4 = gr.Button("🏛️ Carreras y TSU", size="sm")
        btn_nuevo = gr.Button("🧹 Nueva conversación", size="sm")
    with gr.Group(elem_id="inputbar"):
        with gr.Row():
            voz = gr.Audio(sources=["microphone"], type="filepath", show_label=False, scale=1)
            txt = gr.Textbox(placeholder="Escribe o dime tu pregunta…", show_label=False, scale=5)
            btn_txt = gr.Button("➤", variant="primary", scale=1)
        with gr.Row():
            btn_voz = gr.Button("🎤 Enviar mi mensaje de voz", size="sm")
    with gr.Accordion("🛠️ Panel de archivos (personal autorizado)", open=False):
        clave_in = gr.Textbox(label="Clave de acceso", type="password")
        btn_clave = gr.Button("🔓 Entrar")
        with gr.Column(visible=False) as zona_admin:
            archivo = gr.File(label="Documento (TXT o PDF)")
            cat = gr.Dropdown(["Horarios", "Exámenes", "Convocatorias", "Eventos", "Avisos", "TSU"], value="Avisos", label="Categoría")
            vig = gr.Textbox(label="Vigente hasta (dd/mm/aaaa)")
            chk = gr.Checkbox(value=True, label="🔄 Reemplazar anteriores de esta categoría")
            btn_subir = gr.Button("📤 Subir y enseñar al bot")
            estado = gr.Textbox(label="Estado")
            lista = gr.Textbox(label="Documentos que el bot conoce", lines=4)
            contador_txt = gr.Textbox(label="📊 Preguntas atendidas")
            btn_listar = gr.Button("🔄 Actualizar lista")
            nombre_borrar = gr.Textbox(label="Nombre del documento a borrar")
            btn_borrar = gr.Button("🗑️ Borrar")
            btn_subir.click(subir_doc, [archivo, cat, vig, chk], estado).then(listar_docs, None, lista).then(leer_contador, None, contador_txt)
            btn_listar.click(listar_docs, None, lista).then(leer_contador, None, contador_txt)
            btn_borrar.click(borrar_doc, nombre_borrar, estado).then(listar_docs, None, lista).then(leer_contador, None, contador_txt)

        def desbloquear(clave):
            if clave == CLAVE_ADMIN:
                return gr.Column(visible=True)
            return gr.Column(visible=False)

        btn_clave.click(desbloquear, clave_in, zona_admin)

    btn_txt.click(router, [txt, chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    txt.submit(router, [txt, chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    btn_voz.click(procesar_voz, [voz, chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    q1.click(rapida("¿Cuántos créditos necesito para titularme en Traducción?"), [chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    q2.click(rapida("¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?"), [chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    q3.click(rapida("¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?"), [chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    q4.click(rapida("¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?"), [chatbot, estado_admin], [chatbot, audio_out, estado_admin])
    btn_nuevo.click(limpiar_chat, None, [chatbot, audio_out, estado_admin])

demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)), theme=gr.themes.Soft(primary_hue=gr.themes.colors.green), css=CSS)
