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

VERSION = "v20-2026-08-23"

BASE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(BASE, "Manual_Aspirantes_Idiomas_UABC.txt")
CARPETA = os.path.join(BASE, "datos_bot")
AUDIOS = os.path.join(BASE, "audios")
IMGS = os.path.join(BASE, "posters")
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
for d in (AUDIOS, CARPETA, CONVS, IMGS, FEEDBACK):
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
    "Admision": "admision.mxl@uabc.edu.mx",
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
DIAS = {0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves", 4: "viernes", 5: "sabado", 6: "domingo"}
MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
MESES_INV = {v: k for k, v in MESES.items()}
MESES_ALT = "(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
EXT_IMG = (".png", ".jpg", ".jpeg", ".webp")
PROMPT_POSTER = "Este es un anuncio o poster institucional. Extrae TODA la informacion util (que evento, quien invita, fecha, hora, lugar, contacto, requisitos) y devuelvela como texto claro en espanol, sin comentarios."

def fecha_hoy_es():
    n = datetime.now()
    return f"{DIAS[n.weekday()]} {n.day} de {MESES[n.month]} de {n.year}"

def detectar_idioma(texto):
    t = (texto or "").lower()
    fr_st = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplom", "traduction", "salut", "credit", "je ", "etud", "francais", "voud", "veux", "quel", "quelle", "aime", "les ", "des ", "anglais"]
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
        "es": "Para titularte en la Licenciatura en Traduccion (LT) necesitas 349 creditos: 237 obligatorios, 102 optativos y 10 de practicas. Detalles: idiomas.mxl.uabc.mx o 686-689-0825.",
        "en": "To graduate from Translation (LT) you need 349 credits. Details: idiomas.mxl.uabc.mx or 686-689-0825.",
        "fr": "Pour diplomer en Traduction (LT) il faut 349 credits. Details: idiomas.mxl.uabc.mx ou 686-689-0825."}),
    (["carrera", "tsu", "tecnico", "programas", "traduc", "translation", "traduction"], {
        "es": "La Facultad ofrece Licenciaturas en Ensenanza de Lenguas (LEL) y Traduccion (LT), y el TSU. Consulta idiomas.mxl.uabc.mx o 686-689-0825.",
        "en": "The Faculty offers Language Teaching (LEL) and Translation (LT) degrees plus a TSU. See idiomas.mxl.uabc.mx.",
        "fr": "La Faculte offre les licences LEL et LT et un TSU. Voir idiomas.mxl.uabc.mx."}),
    (["frances", "french", "francais", "ingles", "english", "anglais", "study", "estudiar", "etud", "curso", "cours", "cec", "horario"], {
        "es": "El CEC ofrece cursos de ingles, frances, aleman, italiano, portugues, ruso, mandarin, japones, coreano y espanol, en formatos semanal, sabatino, intensivo e intersemestral. Grupos en cecuabc.com. Informes: recepcionmxl@uabc.edu.mx o 686 841-82-91 ext. 300.",
        "en": "The CEC offers English, French, German, Italian, Portuguese, Russian, Mandarin, Japanese, Korean and Spanish courses. Groups at cecuabc.com.",
        "fr": "Le CEC propose des cours d'anglais, francais, allemand, italien, portugais, russe, mandarin, japonais, coreen et espagnol. Groupes sur cecuabc.com."}),
    (["admision", "requisito", "admission"], {
        "es": "Para ingresar: 1) concluir bachillerato, 2) certificado/acta/CURP, 3) registro en el portal (agosto y enero), 4) Examen de Seleccion. No se requiere ingles avanzado. Fechas: admision.uabc.mx.",
        "en": "To enter: finish high school, certificates, register (Aug/Jan), take the Selection Exam. No advanced English needed. Dates: admision.uabc.mx.",
        "fr": "Pour entrer: terminer le lycee, certificats, s'inscrire (aout/janvier), passer l'Examen. Dates: admision.uabc.mx."}),
    (["que haces", "what do you do", "ayudar", "help", "sirves", "puedes hacer"], {
        "es": "Te informo sobre creditos, CEC, admision, carreras, avisos y a QUIEN acudir por cada tema, en espanol, ingles o frances: te leo o te escucho.",
        "en": "I cover credits, CEC, admission, degrees, notices and WHO to contact for each topic: I read you or listen to you.",
        "fr": "Je couvre credits, CEC, admission, licences, avis et QUI contacter : je vous lis ou vous ecoute."}),
]

def _limpiar_doc(texto):
    lineas = []
    for ln in (texto or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("===") or s.startswith("DOCUMENTO"):
            continue
        lineas.append(s)
    return "\n".join(lineas)

def _tokens(t):
    return set(re.findall(r"[a-záéíóúñü$0-9]+", (t or "").lower()))

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
    if any(k in p for k in ("semana", "evento", "hoy", "manana", "pronto", "avisos", "hay")):
        frescos = [t for t in docs.values() if any(hoy <= f <= horizonte for f in _fechas_doc(t))][:2]
        if frescos:
            return "Avisos oficiales recientes:\n\n" + "\n\n".join(t[:500] for t in frescos)
    qt = _tokens(pregunta)
    scored = sorted(((len(qt & _tokens(t)), t) for t in docs.values()), reverse=True)
    if scored and scored[0][0] >= 3:
        return "Segun la informacion oficial: " + scored[0][1][:600]
    return ""

def sistema_prompt(contexto):
    return (
        f"Hoy es {fecha_hoy_es()}. Eres UABCBot Idiomas de la Facultad de Idiomas UABC Mexicali. "
        "Responde en el idioma de la pregunta, conciso. Si preguntan COSTOS da la cifra exacta disponible. "
        "NUNCA repitas la pregunta. FECHAS: primero eventos de los proximos 14 dias. "
        "REGLAS: responde solo lo preguntado; no copies nombres de archivo ni ===; reformula. "
        "Si no aparece, sugiere 686-689-0825 / idiomas.mxl@uabc.edu.mx. "
        f"\nINFORMACION:\n{contexto}"
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
    return not (texto.startswith("Avisos") or texto.startswith("Segun") or len(texto) < 60 or "===" in texto or "documento " in t or len(texto) > 900)

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
    suf = {"es": " (Responde en espanol, conciso.)", "en": " (Answer in English, concise.)", "fr": " (Reponds en francais, concis.)"}[lang]
    pregunta_final = pregunta + suf
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    
    # Groq primero (gratis), luego Gemini (gratis), ultimo OpenRouter (pago)
    texto = llamar_openai(sp, hist, pregunta_final, GROQ_URL, GROQ_KEY, ["llama-3.1-70b-versatile", "llama-3.1-8b-instant"])
    if not _es_valida(texto):
        texto = llamar_gemini(cliente_gemini, sp, hist, pregunta_final)
    if not _es_valida(texto):
        texto = llamar_gemini(cliente_gemini2, sp, hist, pregunta_final)
    if not _es_valida(texto):
        texto = llamar_openai(sp, hist, pregunta_final, OR_URL, OR_KEY, ["deepseek/deepseek-v4-flash"])
    
    if not _es_valida(texto):
        fb = respuesta_de_documentos(pregunta)
        if fb:
            return fb, lang
    if not _es_valida(texto):
        texto = "Motores saturados. Intenta en unos segundos."
    texto = re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto).strip()
    if _es_cacheable(texto):
        cache[clave] = [texto, lang]
        _guardar_cache(cache)
    return texto, lang

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
                        "Transcribe este audio (es/en/fr). Solo la transcripcion.",
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

app = FastAPI()

@app.get("/api/version")
async def api_version():
    return {"version": VERSION}

FAQ = [
    (["credito", "titular", "titul"], "Cuantos creditos necesito para titularme en Traduccion?"),
    (["costo", "cuesta", "precio", "inscri"], "Cuanto cuesta inscribirme a las clases de ingles?"),
    (["horario", "cec"], "Cuales son los horarios del CEC?"),
    (["admision", "requisito"], "Cuales son los requisitos de admision?"),
    (["carrera", "tsu", "tecnico"], "Que carreras y programas tecnicos ofrece?"),
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

def github_subir(ruta_repo, contenido_bytes):
    if not GH_TOKEN or not GH_REPO:
        return "(sin respaldo GitHub)"
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=15)
        data = {"message": f"bot: actualiza {ruta_repo}", "content": base64.b64encode(contenido_bytes).decode()}
        if r.status_code == 200 and r.json().get("sha"):
            data["sha"] = r.json()["sha"]
        q = requests.put(url, json=data, headers=headers, timeout=25)
        return "Respaldo en GitHub listo." if q.status_code in (200, 201) else "No respaldado."
    except Exception:
        return "No respaldado."

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
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: sin limite ===\n"
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
            return "Acceso concedido. Escribe tu aviso o usa el panel. Escribe SALIR para cerrar.", None, state
        return "Clave incorrecta.", None, state
    if state.get("active"):
        if texto.upper() == "SALIR":
            state["active"] = False
            return "Sesion cerrada.", None, state
        nuevo, resp = guardar_aviso(texto)
        return f"Publicado al instante. {resp}", None, state
    if "administraci" in texto.lower():
        state["pending"] = True
        return "Escribe la clave de acceso.", None, state
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
        return {"ok": False, "error": "Usuario >= 3 y clave >= 4 caracteres."}
    users = _jload(USERS, {})
    if u in users:
        return {"ok": False, "error": "Ese usuario ya existe; inicia sesion."}
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
        respuesta = f"Error interno: {type(e).__name__}: {e}"
        audio = None
        state = st
    return {"reply": respuesta, "audio": audio, "state": state}

@app.post("/api/voice")
async def api_voice(audio: UploadFile = File(...), hist: str = Form("[]"), state: str = Form("{}"), lang: str = Form("auto")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"texto": "", "reply": "No logre escuchar bien. Intenta de nuevo mas cerca del microfono.", "audio": None, "state": state}
    st = json.loads(state)
    if not (st.get("active") or st.get("pending")):
        log_uso(texto, lang, "voz")
    respuesta, lang2, state2 = router(texto, json.loads(hist), st, lang)
    aud = await producir_audio(respuesta, lang2)
    return {"texto": texto, "reply": respuesta, "audio": aud, "state": state2}

@app.post("/api/voice_note")
async def voice_note(audio: UploadFile = File(...), categoria: str = Form("Avisos")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"estado": "No logre escuchar la nota."}
    nuevo, resp = guardar_aviso(texto, categoria)
    return {"estado": f"Nota de voz publicada: {nuevo}. {resp}"}

@app.post("/api/unlock")
async def api_unlock(req: Request):
    d = await req.json()
    return {"ok": d.get("clave") == CLAVE_ADMIN}

@app.post("/api/report")
async def report(req: Request):
    d = await req.json()
    if d.get("clave") != CLAVE_ADMIN:
        return {"error": "Clave incorrecta"}
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
    contenido = (
        f"=== Feedback {ts} | Area: {area} | Reenviar a: {AREAS_RESP.get(area, AREAS_RESP['Otro'])} ===\n"
        f"PREGUNTA DEL USUARIO: {d.get('pregunta','')}\n"
        f"RESPUESTA DEL BOT: {d.get('respuesta','')}\n"
        f"COMENTARIO: {d.get('comentario','')}\n"
    )
    with open(os.path.join(FEEDBACK, ts + ".txt"), "w", encoding="utf-8") as f:
        f.write(contenido)
    github_subir(f"feedback/{ts}.txt", contenido.encode("utf-8"))
    return {"ok": True}

@app.get("/api/feedback/list")
async def api_feedback_list(clave: str = ""):
    if clave != CLAVE_ADMIN:
        return {"items": ["Clave incorrecta"]}
    out = []
    for fn in sorted(os.listdir(FEEDBACK), reverse=True)[:10]:
        try:
            with open(os.path.join(FEEDBACK, fn), encoding="utf-8") as f:
                out.append(f.read())
        except Exception:
            pass
    return {"items": out or ["Sin feedbacks aun."]}

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
            return {"estado": "Vision no disponible. Pega el texto del poster en el cuadro y pulsa Subir."}
        iname = str(uuid.uuid4()) + ext
        with open(os.path.join(IMGS, iname), "wb") as f:
            f.write(data)
        texto = texto + f"\nPoster original: /img/{iname}"
    elif data:
        tmp = os.path.join(BASE, "tmp_" + nombre_orig)
        with open(tmp, "wb") as f:
            f.write(data)
        texto = extraer_texto(tmp, nombre_orig) or texto
        os.remove(tmp)
    if not texto:
        return {"estado": "Elige un archivo o pega el texto del aviso en el cuadro."}
    if reemplazar == "1":
        for fn in list(os.listdir(CARPETA)):
            if fn.endswith(f"_{categoria}.txt"):
                os.remove(os.path.join(CARPETA, fn))
                github_borrar(f"datos_bot/{fn}")
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia or 'sin limite'} ===\n"
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(cab + texto)
    resp = github_subir(f"datos_bot/{nuevo}", (cab + texto).encode("utf-8"))
    return {"estado": f"Guardado como {nuevo}. {resp}"}

@app.post("/api/delete")
async def api_delete(req: Request):
    d = await req.json()
    if d.get("clave") != CLAVE_ADMIN:
        return {"estado": "Clave incorrecta"}
    nombre = (d.get("nombre") or "").strip()
    ruta = os.path.join(CARPETA, nombre)
    if os.path.exists(ruta):
        os.remove(ruta)
        github_borrar(f"datos_bot/{nombre}")
        return {"estado": f"{nombre} eliminado (tambien del respaldo)."}
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
    out = {"version": VERSION, "gemini": bool(cliente_gemini), "groq": bool(GROQ_KEY), "openrouter": bool(OR_KEY)}
    try:
        t, l = responder("Di solo la palabra: listo", [])
        out["respuesta"] = t[:100]
    except Exception as e:
        out["error_texto"] = f"{type(e).__name__}: {e}"
    return out

@app.post("/api/conv/save")
async def conv_save(req: Request):
    d = await req.json()
    cid = re.sub(r"[^a-zA-Z0-9_-]", "", d.get("id", ""))[:40] or "c"
    with open(os.path.join(CONVS, cid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": cid, "user": d.get("user", ""), "titulo": d.get("titulo", "Conversacion"), "fecha": datetime.now().isoformat(), "msgs": d.get("msgs", [])}, f, ensure_ascii=False)
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
                out.append({"id": d["id"], "titulo": d.get("titulo", "Conversacion"), "fecha": d.get("fecha", "")})
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
<title>UABCBot Idiomas - Facultad de Idiomas de la UABC en Mexicali</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: #eef1f4; }
  #toast { display: none; position: fixed; top: 12px; left: 50%; transform: translateX(-50%); color: #fff; padding: 13px 22px; border-radius: 14px; font-size: 14.5px; z-index: 99; box-shadow: 0 4px 16px rgba(0,0,0,.35); max-width: 92%; text-align: center; }
  .wrap { max-width: 1400px; margin: 0 auto; height: 100vh; display: flex; flex-direction: row; }
  #side { width: 280px; background: #004d38; color: #fff; padding: 14px 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
  #side b { font-size: 14px; }
  #side button { background: rgba(255,255,255,.12); color: #fff; border: none; border-radius: 10px; padding: 9px 10px; text-align: left; cursor: pointer; font-size: 12.5px; }
  #side button:hover { background: rgba(255,255,255,.25); }
  main { flex: 1; display: flex; flex-direction: column; height: 100vh; }
  header { background: linear-gradient(135deg, #00684a, #00855f); color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; border-radius: 0 0 18px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.15); flex-wrap: wrap; }
  header img { width: 54px; height: 54px; background: #fff; border-radius: 12px; padding: 3px; }
  header h1 { font-size: 17px; } header p { font-size: 12px; opacity: .85; }
  .langs { display: flex; gap: 5px; margin-left: 14px; flex-wrap: wrap; }
  .langs button { font-size: 11px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: transparent; color: #fff; cursor: pointer; }
  .langs button.on { background: #f7941d; border-color: #f7941d; font-weight: 700; }
  .utils { display: flex; gap: 5px; margin-left: auto; }
  .utils button { font-size: 14px; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: rgba(255,255,255,.15); color: #fff; cursor: pointer; }
  .utils button:hover { background: rgba(255,255,255,.3); }
  .hbtn { background: rgba(255,255,255,.15); border: none; border-radius: 999px; width: 36px; height: 36px; cursor: pointer; font-size: 16px; }
  #nuevo { margin-left: auto; }
  #chat { flex: 1; overflow-y: auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 82%; display: flex; flex-direction: column; gap: 4px; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.bot { align-self: flex-start; align-items: flex-start; }
  .bub { padding: 10px 14px; border-radius: 16px; font-size: calc(14.5px * var(--fs, 1)); line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,.12); white-space: pre-wrap; }
  .user .bub { background: #d9f6c8; border-bottom-right-radius: 4px; }
  .bot .bub { background: #fff; border-bottom-left-radius: 4px; }
  .msg audio { width: 260px; max-width: 100%; }
  .think .bub { background: #fff; color: #666; font-style: italic; }
  .dots::after { content: ''; animation: pts 1.2s steps(4) infinite; }
  @keyframes pts { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75% { content: '...'; } }
  .opts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .opts button { font-size: calc(12.5px * var(--fs, 1)); padding: 7px 11px; border-radius: 999px; border: 1px solid #00855f; background: #f2fbf6; color: #00684a; cursor: pointer; }
  .opts button:hover { background: #00855f; color: #fff; }
  .nota { display: block; margin-top: 9px; font-size: calc(12px * var(--fs, 1)); color: #888; }
  .bar { display: flex; gap: 8px; padding: 10px 12px 14px; align-items: center; }
  #mic { width: 46px; height: 46px; border-radius: 50%; border: none; background: #00684a; color: #fff; font-size: 19px; cursor: pointer; flex-shrink: 0; }
  #mic.rec { background: #d32f2f; animation: pulso 1s infinite; }
  @keyframes pulso { 50% { transform: scale(1.12); } }
  #inp { flex: 1; border: 1px solid #cfd8dc; border-radius: 999px; padding: 12px 18px; font-size: calc(15px * var(--fs, 1)); outline: none; }
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
  @media (max-width: 900px) { #side { display: none; } #convs { display: block; } }
  @media (min-width: 900px) {
    .bub { font-size: calc(16.5px * var(--fs, 1)); }
    header h1 { font-size: 21px; }
    header p { font-size: 13px; }
    #inp { font-size: calc(17px * var(--fs, 1)); padding: 14px 22px; }
    .msg { max-width: 70%; }
  }
</style>
</head>
<body>
<div id="toast"></div>
<div class="wrap">
  <aside id="side">
    <b>Conversaciones</b>
    <button id="nueva">Nueva conversacion</button>
    <div id="lista"></div>
  </aside>
  <main>
    <header>
      <img src="/logo.png" alt="logo">
      <div><h1>UABCBot Idiomas</h1><p>Facultad de Idiomas de la UABC en Mexicali</p></div>
      <div class="langs">
        <button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button>
      </div>
      <div class="utils">
        <button id="fmenos" title="Reducir letra">A-</button>
        <button id="fmas" title="Aumentar letra">A+</button>
        <button id="full" title="Pantalla completa">Pantalla completa</button>
      </div>
      <button id="convs" class="hbtn" title="Conversaciones">C</button>
      <button id="user" class="hbtn" title="Tu cuenta">U</button>
      <button id="nuevo" class="hbtn" title="Nueva conversacion">N</button>
    </header>
    <button id="gear" title="Personal autorizado">P</button>
    <div id="cdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">X</button><b>Conversaciones</b><div id="lista2"></div></div>
    <div id="udrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">X</button>
      <b>Tu cuenta</b>
      <div id="who"></div>
      <input id="uusr" placeholder="Usuario o correo">
      <input id="ukey" type="password" placeholder="Clave">
      <button id="ureg">Registrarme</button>
      <button id="ulin">Entrar</button>
      <button id="uguest">Seguir como invitado</button>
      <button id="uout">Cerrar sesion</button>
    </div>
    <div id="chat"></div>
    <div id="fbdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">X</button>
      <b>Reportar respuesta no resuelta</b>
      <span class="etiq">Area responsable</span>
      <select id="fbarea">
        <option>Admision</option><option>CEC</option><option>Escolar/Escolaridad</option><option>Egresados/Bolsa de trabajo</option><option>Eventos</option><option>Otro</option>
      </select>
      <span class="etiq">Cuentanos que falto</span>
      <textarea id="fbcom" rows="3" placeholder="Ej. No me dijo la fecha exacta del examen de admision..."></textarea>
      <button id="fbsend">Enviar al responsable</button>
    </div>
    <div id="drawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">X</button>
      <b>Panel de personal</b>
      <input id="clave" type="password" placeholder="Clave de acceso (Enter para entrar)">
      <button id="unlock">Entrar</button>
      <button id="salirp">Salir del panel</button>
      <div id="zona" style="display:none">
        <span class="etiq">1. Categoria del aviso</span>
        <select id="fcat">
          <option>Avisos</option><option>Eventos</option><option>Suspensiones</option><option>Horarios</option><option>Examenes</option><option>Convocatorias</option><option>TSU</option><option>PlanDeEstudios</option>
        </select>
        <span class="etiq">2. Vigente hasta (opcional)</span>
        <input id="fvig" type="date">
        <span class="etiq">3. Elige o arrastra el archivo (TXT, PDF o imagen)</span>
        <div id="drop">Arrastra aqui tu documento o poster<br><small>o toca para elegirlo</small></div>
        <input id="ffile" type="file" style="display:none">
        <span class="etiq">Texto del poster (plan B recomendado para imagenes)</span>
        <div class="ayuda">Si subes una IMAGEN y el motor de vision esta saturado, copia y pega aqui lo que dice el poster (evento, fecha, hora, lugar) y se publicara al instante sin esperar.</div>
        <textarea id="ftexto" rows="4" placeholder="Ejemplo: Platica para Potenciales a Egresar. Martes 18 de agosto, 12:00 y 16:00 hrs, Sala de Usos Multiples. Informes: Mtra. Dulce Rodriguez, egresados__idiomas__mxl@uabc.edu.mx"></textarea>
        <button id="fsubir">Subir y publicar</button>
        <button id="nota">Grabar nota de voz</button>
        <button id="ldocs">Ver documentos</button>
        <button id="lfb">Ver feedbacks</button>
        <button id="rep">Reporte de uso</button>
        <div id="dlist"></div>
        <span class="etiq">Borrar un documento</span>
        <input id="fdel" placeholder="Nombre del documento a borrar (Enter borra)">
        <button id="bdel">Borrar</button>
        <div id="fest"></div>
      </div>
    </div>
    <div class="bar">
      <button id="mic">M</button>
      <input id="inp" placeholder="Escribe o dime tu pregunta...">
      <button id="send">E</button>
      <button id="fb" title="No te resolvio? Reportalo">R</button>
    </div>
  </main>
</div>
<script>
let hist = [], state = {pending:false, active:false}, langPref = "auto", rec = null, rec2 = null, chunks = [], currentId = uid(), droppedFile = null, thinkTimer = null, thinkSec = 0, toastTimer = null, lastPregunta = "", lastRespuesta = "", fontScale = 1;
let currentUser = localStorage.getItem('uabc_user') || "";
const chat = document.getElementById('chat'), inp = document.getElementById('inp');
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function uid(){ return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2,7); }
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

const TEXTOS = {
  es: {
    bienvenida: "Hola! Soy UABCBot Idiomas, el asistente de la Facultad de Idiomas de la UABC en Mexicali. Toca una opcion o escribe/dime tu pregunta en espanol, ingles o frances.",
    nota: "Personal docente: escribe o di administracion. Si una respuesta no te resuelve, toca Reportar.",
    sugerencias: [
      {q: "Cuantos creditos necesito para titularme en Traduccion?", t: "Creditos para titularme"},
      {q: "Cuales son los horarios del Centro de Ensenanza de Lenguas (CEC)?", t: "Horarios del CEC"},
      {q: "Cuales son los requisitos de admision a la Facultad de Idiomas?", t: "Requisitos de admision"},
      {q: "Que carreras y programas tecnicos ofrece la Facultad de Idiomas?", t: "Carreras y TSU"}
    ]
  },
  en: {
    bienvenida: "Hi! I am UABCBot Idiomas, the assistant of the Faculty of Languages of UABC in Mexicali. Tap an option or type/tell me your question in Spanish, English or French.",
    nota: "Teaching staff: type or say administracion. If an answer does not solve your question, tap Report.",
    sugerencias: [
      {q: "How many credits do I need to graduate from Translation?", t: "Credits to graduate"},
      {q: "What are the schedules of the Language Teaching Center (CEC)?", t: "CEC schedules"},
      {q: "What are the admission requirements for the Faculty of Languages?", t: "Admission requirements"},
      {q: "What degrees and technical programs does the Faculty of Languages offer?", t: "Degrees and TSU"}
    ]
  },
  fr: {
    bienvenida: "Bonjour! Je suis UABCBot Idiomas, l'assistant de la Faculte de Langues de l'UABC a Mexicali. Touchez une option ou ecrivez/dites-moi votre question en espagnol, anglais ou francais.",
    nota: "Personnel enseignant: ecrivez ou dites administracion. Si une reponse ne vous aide pas, touchez Signaler.",
    sugerencias: [
      {q: "Combien de credits faut-il pour obtenir son diplome en Traduction?", t: "Credits pour diplomer"},
      {q: "Quels sont les horaires du Centre d'Enseignement des Langues (CEC)?", t: "Horaires du CEC"},
      {q: "Quelles sont les conditions d'admission a la Faculte de Langues?", t: "Conditions d'admission"},
      {q: "Quelles licences et programmes techniques offre la Faculte de Langues?", t: "Licences et TSU"}
    ]
  }
};

async function welcome(){
  const L = langPref === 'auto' ? 'es' : langPref;
  const t = TEXTOS[L] || TEXTOS.es;
  let opts = t.sugerencias;
  try {
    const d = await (await fetch('/api/topfaq')).json();
    if (d && d.length) {
      opts = d.map(x => ({q: x.q, t: "Popular: " + (x.q.length > 40 ? x.q.slice(0,40) + "..." : x.q)}));
    }
  } catch(e) {}
  const d = document.createElement('div'); d.className = 'msg bot';
  d.innerHTML = '<div class="bub">' + t.bienvenida + '<div class="opts">'
    + opts.map(o => '<button data-q="' + esc(o.q) + '">' + esc(o.t) + '</button>').join('')
    + '</div><span class="nota">' + t.nota + '</span></div>';
  chat.appendChild(d);
  d.querySelectorAll('[data-q]').forEach(b => b.onclick = () => send(b.dataset.q));
  try {
    const audioResp = await fetch('/api/tts?lang=' + L + '&texto=' + encodeURIComponent(t.bienvenida));
    const audioData = await audioResp.json();
    if (audioData.url) {
      const au = document.createElement('audio');
      au.controls = true;
      au.src = audioData.url;
      d.querySelector('.bub').appendChild(au);
    }
  } catch(e) {}
  chat.scrollTop = chat.scrollHeight;
}

function thinking(){
  removeThink();
  const d = document.createElement('div'); d.className = 'msg bot think'; d.id = 'think';
  d.innerHTML = '<div class="bub">Pensando... <span id="tsec">0</span> s</div>';
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  thinkSec = 0;
  thinkTimer = setInterval(() => { thinkSec++; const e = document.getElementById('tsec'); if (e) e.textContent = thinkSec; }, 1000);
}
function removeThink(){
  if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null; }
  const t = document.getElementById('think'); if (t) t.remove();
}
function refreshWho(){
  document.getElementById('who').innerText = currentUser ? 'Sesion: ' + currentUser + ' (tus conversaciones se guardan)' : 'Modo invitado: sin memoria de conversaciones.';
}
function saveConv(){
  if (!currentUser) return;
  const titulo = ((hist.find(m => m.role === 'user') || {}).content || 'Nueva conversacion').slice(0, 40);
  fetch('/api/conv/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: currentId, user: currentUser, titulo, msgs: hist})}).then(() => loadList());
}
async function loadList(){
  if (!currentUser) {
    const msg = '<small>Invitado: sin memoria. Registrarte para guardar tus conversaciones.</small>';
    document.getElementById('lista').innerHTML = msg;
    document.getElementById('lista2').innerHTML = msg;
    return;
  }
  const d = await (await fetch('/api/conv/list?user=' + encodeURIComponent(currentUser))).json();
  const html = d.map(c => '<button class="item" data-id="' + c.id + '">' + esc(c.titulo) + '</button>').join('');
  document.getElementById('lista').innerHTML = html || '<small>Sin conversaciones aun.</small>';
  document.getElementById('lista2').innerHTML = html || '<small>Sin conversaciones aun.</small>';
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
  hist.push({role:'user', content: esClave ? '******' : msg});
  if (esClave) setTimeout(() => { el.querySelector('.bub').textContent = 'Clave'; }, 30000);
  inp.value = '';
  lastPregunta = msg;
  thinking();
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg, hist: hist.slice(-7), state, lang: langPref})});
  const d = await r.json(); removeThink(); state = d.state;
  lastRespuesta = d.reply;
  hist.push({role:'assistant', content: d.reply, audio: d.audio}); bubble('bot', d.reply, d.audio);
  saveConv();
}
async function loadDocs(){
  const d = await (await fetch('/api/docs')).json();
  document.getElementById('dlist').innerText = (d.docs || []).join('\\n') || 'Sin documentos.';
}

function applyLang(newLang){
  langPref = newLang;
  document.querySelectorAll('.langs button').forEach(b => b.classList.remove('on'));
  document.getElementById('L' + (newLang === 'auto' ? 'auto' : newLang)).classList.add('on');
  chat.innerHTML = '';
  welcome();
}

document.getElementById('send').onclick = () => send(inp.value);
inp.onkeydown = e => { if (e.key === 'Enter') send(inp.value); };
document.getElementById('nuevo').onclick = nueva;
document.getElementById('nueva').onclick = nueva;
document.getElementById('convs').onclick = () => { const d = document.getElementById('cdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; loadList(); };
document.getElementById('user').onclick = () => { const d = document.getElementById('udrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; refreshWho(); };
document.getElementById('fb').onclick = () => {
  if (!lastRespuesta) { avisar('Aun no hay respuestas que reportar.', 'error'); return; }
  const d = document.getElementById('fbdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block';
};
document.getElementById('fbsend').onclick = async () => {
  await fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({pregunta: lastPregunta, respuesta: lastRespuesta, comentario: document.getElementById('fbcom').value, area: document.getElementById('fbarea').value})});
  document.getElementById('fbcom').value = '';
  document.getElementById('fbdrawer').style.display = 'none';
  avisar('Gracias: tu reporte llego al responsable del area y alimentara al bot.', 'ok');
};
document.getElementById('ureg').onclick = async () => {
  const d = await (await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('Bienvenido, ' + currentUser + '. Tus conversaciones se guardaran.', 'ok');
};
document.getElementById('ulin').onclick = async () => {
  const d = await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) { avisar(d.error, 'error'); return; }
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
  avisar('Sesion iniciada: ' + currentUser, 'ok');
};
document.getElementById('uguest').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; };
document.getElementById('uout').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; avisar('Sesion cerrada.'); };

[['auto','auto'],['es','es'],['en','en'],['fr','fr']].forEach(([id, val]) => {
  document.getElementById('L' + id).onclick = () => applyLang(val);
});

document.getElementById('fmas').onclick = () => {
  fontScale = Math.min(2.0, fontScale + 0.1);
  document.documentElement.style.setProperty('--fs', fontScale);
  avisar('Letra: ' + Math.round(fontScale * 100) + '%', 'ok');
};
document.getElementById('fmenos').onclick = () => {
  fontScale = Math.max(0.8, fontScale - 0.1);
  document.documentElement.style.setProperty('--fs', fontScale);
  avisar('Letra: ' + Math.round(fontScale * 100) + '%', 'ok');
};

document.getElementById('full').onclick = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
};

const drop = document.getElementById('drop');
function marcarArchivo(f){
  droppedFile = f;
  drop.innerHTML = 'Archivo: ' + esc(f.name);
  avisar('Archivo listo: ' + f.name + ' - pulsa Subir y publicar.');
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
    if (d.texto) { bubble('user', 'Voz: ' + d.texto); hist.push({role:'user', content: d.texto}); lastPregunta = d.texto; }
    if (d.reply) { bubble('bot', d.reply, d.audio); hist.push({role:'assistant', content: d.reply, audio: d.audio}); lastRespuesta = d.reply; }
    saveConv();
  };
  rec.start(); mic.classList.add('rec');
  avisar('Grabando tu pregunta... toca el microfono para terminar.');
};
document.getElementById('gear').onclick = () => { const d = document.getElementById('drawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; };
document.getElementById('salirp').onclick = () => { state = {pending:false, active:false}; document.getElementById('drawer').style.display = 'none'; document.getElementById('zona').style.display = 'none'; };
document.getElementById('clave').onkeydown = e => { if (e.key === 'Enter') document.getElementById('unlock').click(); };
document.getElementById('fdel').onkeydown = e => { if (e.key === 'Enter') document.getElementById('bdel').click(); };
document.getElementById('unlock').onclick = async () => {
  const r = await fetch('/api/unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})});
  const d = await r.json();
  document.getElementById('zona').style.display = d.ok ? 'block' : 'none';
  if (d.ok) { loadDocs(); avisar('Panel de personal abierto.', 'ok'); }
  else avisar('Clave incorrecta.', 'error');
};
document.getElementById('fsubir').onclick = async () => {
  const f = document.getElementById('ffile').files[0] || droppedFile;
  if (!f && !document.getElementById('ftexto').value.trim()) { avisar('Elige un archivo o pega el texto del aviso en el cuadro.', 'error'); return; }
  avisar('Procesando y publicando... puede tardar unos segundos.');
  const fd = new FormData();
  if (f) fd.append('archivo', f);
  fd.append('categoria', document.getElementById('fcat').value);
  fd.append('vigencia', document.getElementById('fvig').value);
  fd.append('reemplazar', '0');
  fd.append('texto_manual', document.getElementById('ftexto').value);
  const d = await (await fetch('/api/upload', {method:'POST', body: fd})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.startsWith('Guardado') ? 'ok' : 'error');
  loadDocs();
};
document.getElementById('ldocs').onclick = loadDocs;
document.getElementById('lfb').onclick = async () => {
  const d = await (await fetch('/api/feedback/list?clave=' + encodeURIComponent(document.getElementById('clave').value))).json();
  document.getElementById('fest').innerText = (d.items || []).join('\\n------------------\\n');
  avisar('Feedbacks listados abajo.', 'ok');
};
document.getElementById('bdel').onclick = async () => {
  const d = await (await fetch('/api/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value, nombre: document.getElementById('fdel').value})})).json();
  document.getElementById('fest').innerText = d.estado;
  avisar(d.estado, d.estado.includes('eliminado') ? 'ok' : 'error');
  loadDocs();
};
document.getElementById('nota').onclick = async () => {
  if (rec2 && rec2.state === 'recording') { rec2.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  let ch = []; rec2 = new MediaRecorder(stream);
  rec2.ondataavailable = e => ch.push(e.data);
  rec2.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    avisar('Transcribiendo y publicando tu nota...');
    const fd = new FormData();
    fd.append('audio', new Blob(ch, {type:'audio/webm'}), 'nota.webm');
    fd.append('categoria', document.getElementById('fcat').value);
    const d = await (await fetch('/api/voice_note', {method:'POST', body: fd})).json();
    document.getElementById('fest').innerText = d.estado;
    avisar(d.estado, d.estado.includes('publicada') ? 'ok' : 'error');
    loadDocs();
  };
  rec2.start();
  avisar('Grabando nota... toca de nuevo para terminar y publicar.');
};
document.getElementById('rep').onclick = async () => {
  const d = await (await fetch('/api/report', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})})).json();
  if (d.error) { avisar(d.error, 'error'); return; }
  document.getElementById('fest').innerText = 'Total: ' + d.total + ' - Hoy: ' + d.hoy + ' - Idiomas: ' + JSON.stringify(d.idiomas)
    + '\\n\\nMas frecuentes:\\n' + d.top.map((x, i) => (i+1) + '. ' + x[0] + ' (' + x[1] + ')').join('\\n');
  avisar('Reporte listo en el panel.', 'ok');
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
