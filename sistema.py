import os, re, tempfile
import edge_tts
from config import generar, busqueda_web, VOCES

SYSTEM = """Eres UABCBot Idiomas, asistente virtual de la Facultad de Idiomas Mexicali de la UABC y del Centro de Educación Continua (CEC).
Hoy es {fecha}. Usa esta fecha para decir si un periodo del calendario está en curso, próximo o concluido.

CONTEXTO OFICIAL BASE:
{contexto_base}

INFORMACIÓN ADICIONAL RECIENTE (prioriza esta si coincide con la pregunta):
{contexto_adicional}

REGLAS:
1. Inicia SIEMPRE tu respuesta con la etiqueta [LANG: xx], donde xx es el idioma de la pregunta (es, en, fr, pt). Después responde EN ESE MISMO IDIOMA.
2. Si la INFORMACIÓN ADICIONAL responde la pregunta, úsala como fuente principal (es la más reciente).
3. Tono amable, claro y motivador; tu público son aspirantes de preparatoria y público general.
4. Si la respuesta NO está en ningún contexto, responde ÚNICAMENTE con el texto [NEEDS_WEB].
5. Si te incluyen RESULTADOS WEB, úsalos y cita la fuente al final con su liga.
6. Nunca inventes fechas ni datos.
7. Si no tienes respuesta confiable, da el contacto oficial (Tel: +52 686.689.0825, idiomas.mxl.uabc.mx) e invita a reformular.
8. Tu respuesta será leída por una voz: NO uses Markdown, negritas, viñetas, emojis ni listas; escribe en párrafos fluidos."""

def limpiar_respuesta(texto):
    m = re.search(r"\[LANG:\s*([a-z]{2})\]", texto, re.I)
    lang = m.group(1).lower() if m else "es"
    limpio = re.sub(r"\[LANG:\s*[a-z]{2}\]", "", texto, flags=re.I).strip()
    limpio = re.sub(r"https?://\S+", "", limpio)
    limpio = re.sub(r"\*\*(.*?)\*\*", r"\1", limpio)
    limpio = re.sub(r"#+\s*", "", limpio)
    limpio = re.sub(r"^[\*\-\+]\s*", "", limpio, flags=re.MULTILINE)
    limpio = re.sub("[\U0001F300-\U0001FAFF☀-➿]", "", limpio)
    limpio = re.sub(r"\n{2,}", " ", limpio)
    return limpio.strip(), lang

def obtener_contexto():
    dir_base = os.path.dirname(os.path.abspath(__file__))
    ruta_manual = os.path.join(dir_base, "Manual_Aspirantes_Idiomas_UABC.txt")
    with open(ruta_manual, encoding="utf-8") as f:
        base = f.read()
    extra = ""
    datos = os.path.join(dir_base, "datos_bot")
    if os.path.isdir(datos):
        for fn in sorted(os.listdir(datos)):
            if fn.endswith(".txt"):
                with open(os.path.join(datos, fn), encoding="utf-8") as f:
                    extra += f.read() + "\n\n"
    return base, extra or "Sin información adicional por ahora."

def responder(pregunta, historial):
    from datetime import date
    base, extra = obtener_contexto()
    sys = SYSTEM.format(fecha=date.today().strftime("%d/%m/%Y"),
                        contexto_base=base, contexto_adicional=extra)
    contents = historial + [{"role": "user", "parts": [{"text": pregunta}]}]
    r = generar(contents, sys)
    texto = r.text
    if "[NEEDS_WEB]" in texto:
        web = busqueda_web(pregunta)
        r = generar(contents, sys + "\n\nRESULTADOS WEB OFICIALES:\n" + web)
        texto = r.text
    return limpiar_respuesta(texto)

def transcribir(audio_bytes):
    from google.genai import types
    for mime in ("audio/webm", "audio/wav", "audio/mp3"):
        try:
            r = generar([types.Part.from_bytes(data=audio_bytes, mime_type=mime),
                         "Escucha este audio. Responde con [LANG: xx] del idioma hablado y en la siguiente línea la transcripción exacta."])
            return limpiar_respuesta(r.text)
        except Exception:
            continue
    return None, "es"

async def generar_voz(texto, lang):
    ruta = tempfile.mktemp(suffix=".mp3")
    await edge_tts.Communicate(texto, VOCES.get(lang, VOCES["es"])).save(ruta)
    return ruta