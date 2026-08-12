import os
import asyncio
import gradio as gr
from datetime import datetime
from sistema import responder, transcribir, generar_voz

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_bot")

def procesar_texto(pregunta, historial):
    historial = historial or []
    respuesta, lang = responder(pregunta, [])
    ruta_voz = asyncio.run(generar_voz(respuesta, lang))
    historial.append((pregunta, respuesta))
    return historial, ruta_voz

def procesar_voz(audio_path, historial):
    if not audio_path:
        return historial, None
    with open(audio_path, "rb") as f:
        data = f.read()
    texto, lang = transcribir(data)
    if not texto:
        return historial, None
    return procesar_texto(texto, historial)

def extraer_texto(ruta, nombre):
    if nombre.lower().endswith(".pdf"):
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        return "\n".join((p.extract_text() or "") for p in lector.pages)
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        return f.read()

def subir_doc(archivo, categoria, vigencia):
    if archivo is None:
        return "⚠️ Selecciona un archivo primero."
    os.makedirs(CARPETA, exist_ok=True)
    nombre = os.path.basename(archivo)
    texto = extraer_texto(archivo, nombre)
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia or 'sin límite'} ===\n"
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(cab + texto)
    return f"✅ Guardado como {nuevo}"

def listar_docs():
    if not os.path.isdir(CARPETA):
        return "Aún no hay documentos adicionales."
    archivos = [f for f in sorted(os.listdir(CARPETA)) if f.endswith(".txt")]
    return "\n".join(archivos) or "Aún no hay documentos adicionales."

def borrar_doc(nombre):
    ruta = os.path.join(CARPETA, nombre.strip())
    if os.path.exists(ruta):
        os.remove(ruta)
        return f"🗑️ {nombre} eliminado."
    return "No encontrado."

with gr.Blocks(title="UABCBot Idiomas UABC") as demo:
    gr.Markdown("# 🎓 Asistente Virtual - Facultad de Idiomas UABC")
    gr.Markdown("Pregúntame por texto o por voz, en español, inglés o francés.")
    with gr.Tabs():
        with gr.Tab("💬 Chat"):
            chatbot = gr.Chatbot(height=400, label="Conversación")
            with gr.Row():
                txt = gr.Textbox(label="Escribe tu pregunta")
                btn_txt = gr.Button("Enviar 📨")
            voz = gr.Audio(sources=["microphone"], type="filepath", label="🎤 O graba tu pregunta")
            btn_voz = gr.Button("Enviar voz 🎤")
            audio_out = gr.Audio(label="🔊 Respuesta en audio", type="filepath")

            def enviar_texto(pregunta, hist):
                if not pregunta:
                    return hist, None
                return procesar_texto(pregunta, hist)

            btn_txt.click(enviar_texto, [txt, chatbot], [chatbot, audio_out])
            txt.submit(enviar_texto, [txt, chatbot], [chatbot, audio_out])
            btn_voz.click(procesar_voz, [voz, chatbot], [chatbot, audio_out])
        with gr.Tab("👨‍🏫 Administración"):
            gr.Markdown("Sube horarios, convocatorias o avisos para que el bot los aprenda al instante.")
            archivo = gr.File(label="Documento (TXT o PDF)")
            cat = gr.Dropdown(["Horarios", "Exámenes", "Convocatorias", "Eventos", "Avisos"], value="Avisos", label="Categoría")
            vig = gr.Textbox(label="Vigente hasta (dd/mm/aaaa)", placeholder="28/11/2026")
            btn_subir = gr.Button("📤 Subir y enseñar al bot")
            estado = gr.Textbox(label="Estado")
            lista = gr.Textbox(label="Documentos que el bot conoce", lines=6)
            btn_listar = gr.Button("🔄 Actualizar lista")
            nombre_borrar = gr.Textbox(label="Nombre del documento a borrar")
            btn_borrar = gr.Button("🗑️ Borrar")
            btn_subir.click(subir_doc, [archivo, cat, vig], estado).then(listar_docs, None, lista)
            btn_listar.click(listar_docs, None, lista)
            btn_borrar.click(borrar_doc, nombre_borrar, estado).then(listar_docs, None, lista)

demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))