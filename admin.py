import os
import streamlit as st
from datetime import datetime

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_bot")

def extraer_texto(archivo):
    if archivo.name.lower().endswith(".pdf"):
        import io
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(archivo.getvalue()))
        return "\n".join((p.extract_text() or "") for p in lector.pages)
    return archivo.getvalue().decode("utf-8", errors="ignore")

def panel_admin():
    st.title("👨‍🏫 Panel de Administración")
    st.write("Sube horarios, convocatorias o avisos nuevos para que el bot los aprenda al instante.")
    os.makedirs(CARPETA, exist_ok=True)

    archivo = st.file_uploader("Documento (TXT o PDF)", type=["txt", "pdf"])
    categoria = st.selectbox("Categoría", ["Horarios", "Exámenes", "Convocatorias", "Eventos", "Avisos"])
    vigencia = st.date_input("Vigente hasta")

    if st.button("📤 Subir y enseñar al bot") and archivo is not None:
        texto = extraer_texto(archivo)
        nombre = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
        cabecera = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia.strftime('%d/%m/%Y')} ===\n"
        with open(os.path.join(CARPETA, nombre), "w", encoding="utf-8") as f:
            f.write(cabecera + texto)
        st.success("✅ El bot ya conoce esta información.")

    st.subheader("📚 Documentos que el bot conoce")
    archivos = [f for f in sorted(os.listdir(CARPETA)) if f.endswith(".txt")]
    if not archivos:
        st.info("Aún no hay documentos adicionales.")
    for fn in archivos:
        col1, col2 = st.columns([4, 1])
        col1.write(f"📄 {fn}")
        if col2.button("🗑️", key=fn):
            os.remove(os.path.join(CARPETA, fn))
            st.rerun()