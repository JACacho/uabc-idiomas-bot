import os
import re
import uuid
import json
import base64
import asyncio
import hashlib
import secrets
import requests as http_requests
from datetime import datetime
from collections import Counter
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
import sistema as _sist
from sistema import responder, transcribir, generar_voz

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE, "datos_bot")
AUDIOS = os.path.join(BASE, "audios")
IMGS = os.path.join(BASE, "posters")
CONVS = os.path.join(BASE, "conversaciones")
CONTADOR = os.path.join(BASE, "conteo.txt")
USO = os.path.join(BASE, "uso.jsonl")
USERS = os.path.join(BASE, "users.json")
SESSIONS = os.path.join(BASE, "sessions.json")
CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "fimxl2026")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPO", "")
LOGO = os.path.join(BASE, "logo.png")
LOGO_URL = "https://raw.githubusercontent.com/JACacho/uabc-idiomas-bot/main/logo.png"
for d in (AUDIOS, CARPETA, CONVS, IMGS):
    os.makedirs(d, exist_ok=True)

try:
    if not os.path.exists(LOGO):
        r = http_requests.get(LOGO_URL, timeout=10)
        if r.status_code == 200 and r.content:
            with open(LOGO, "wb") as f:
                f.write(r.content)
except Exception:
    pass

app = FastAPI()

FAQ = [
    (["credito", "titular", "titul"], "¿Cuántos créditos necesito para titularme en Traducción?"),
    (["horario", "cec"], "¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?"),
    (["admision", "requisito", "inscri"], "¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?"),
    (["carrera", "tsu", "tecnico", "técnico"], "¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?"),
]

EXT_IMG = (".png", ".jpg", ".jpeg", ".webp")

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
        return "⚠️ Vivo solo en esta sesión (falta token de GitHub)."
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = http_requests.get(url, headers=headers, timeout=15)
        data = {"message": f"bot: actualiza {ruta_repo}", "content": base64.b64encode(contenido_bytes).decode()}
        if r.status_code == 200 and r.json().get("sha"):
            data["sha"] = r.json()["sha"]
        q = http_requests.put(url, json=data, headers=headers, timeout=25)
        return "☁️ Respaldo permanente en GitHub listo." if q.status_code in (200, 201) else "⚠️ No se pudo respaldar en GitHub."
    except Exception:
        return "⚠️ No se pudo respaldar en GitHub."

def github_borrar(ruta_repo):
    if not GH_TOKEN or not GH_REPO:
        return ""
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/contents/{ruta_repo}"
        headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
        r = http_requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and r.json().get("sha"):
            http_requests.delete(url, json={"message": f"bot: borra {ruta_repo}", "sha": r.json()["sha"]}, headers=headers, timeout=25)
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
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: sin límite ===\n"
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
            return "✅ Acceso concedido, profe. Escribe tu aviso tal cual (o usa el panel ⚙️ para documentos, pósters y notas de voz). Escribe SALIR para cerrar.", None, state
        return "❌ Clave incorrecta.", None, state
    if state.get("active"):
        if texto.upper() == "SALIR":
            state["active"] = False
            return "🔒 Sesión de administración cerrada. Vuelvo a modo aspirante.", None, state
        nuevo, resp = guardar_aviso(texto)
        return f"✅ Publicado y aprendido al instante. {resp}", None, state
    if "administraci" in texto.lower():
        state["pending"] = True
        return "🔐 Para entrar al modo de administración, escribe la clave de acceso.", None, state
    pregunta = normalizar_faq(texto)
    suf = {"es": "\n(Responde en español.)", "en": "\n(Answer in English.)", "fr": "\n(Réponds en français.)"}.get(lang_pref, "")
    try:
        respuesta, lang = responder(pregunta + suf, hist or [])
    except Exception:
        respuesta, lang = responder(pregunta, [])
    respuesta = limpiar_tags(respuesta)
    return respuesta, lang if lang_pref == "auto" else lang_pref, state

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
        return {"ok": False, "error": "Usuario ≥ 3 y clave ≥ 4 caracteres."}
    users = _jload(USERS, {})
    if u in users:
        return {"ok": False, "error": "Ese usuario ya existe; inicia sesión."}
    salt = secrets.token_hex(8)
    users[u] = {"salt": salt, "hash": _hash(c, salt)}
    _jdump(USERS, users)
    tok = secrets.token_hex(16)
    ses = _jload(SESSIONS, {})
    ses[tok] = u
    _jdump(SESSIONS, ses)
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
    tok = secrets.token_hex(16)
    ses = _jload(SESSIONS, {})
    ses[tok] = u
    _jdump(SESSIONS, ses)
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
        respuesta = f"⚠️ Error interno: {type(e).__name__}: {e}"
        audio = None
        state = st
    return {"reply": respuesta, "audio": audio, "state": state}

@app.post("/api/voice")
async def api_voice(audio: UploadFile = File(...), hist: str = Form("[]"), state: str = Form("{}"), lang: str = Form("auto")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"texto": "", "reply": "⚠️ No logré escuchar bien. Intenta de nuevo más cerca del micrófono.", "audio": None, "state": state}
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
        return {"estado": "⚠️ No logré escuchar la nota."}
    nuevo, resp = guardar_aviso(texto, categoria)
    return {"estado": f"✅ Nota de voz publicada: {nuevo}. {resp}"}

@app.post("/api/unlock")
async def api_unlock(req: Request):
    d = await req.json()
    return {"ok": d.get("clave") == CLAVE_ADMIN}

@app.post("/api/report")
async def report(req: Request):
    d = await req.json()
    if d.get("clave") != CLAVE_ADMIN:
        return {"error": "❌ Clave incorrecta"}
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

@app.post("/api/upload")
async def api_upload(archivo: UploadFile = File(...), categoria: str = Form("Avisos"), vigencia: str = Form(""), reemplazar: str = Form("0")):
    nombre_orig = archivo.filename or "doc.txt"
    ext = os.path.splitext(nombre_orig)[1].lower()
    data = await archivo.read()
    if ext in EXT_IMG:
        mime = "image/png" if ext == ".png" else "image/jpeg"
        texto = _sist.extraer_imagen(data, mime)
        if not texto:
            return {"estado": "⚠️ No pude leer el póster (el motor de visión está saturado). Intenta de nuevo en un minuto, o usa TXT/PDF."}
        iname = str(uuid.uuid4()) + ext
        with open(os.path.join(IMGS, iname), "wb") as f:
            f.write(data)
        texto = texto + f"\n🖼️ Póster original: /img/{iname}"
    else:
        tmp = os.path.join(BASE, "tmp_" + nombre_orig)
        with open(tmp, "wb") as f:
            f.write(data)
        texto = extraer_texto(tmp, nombre_orig)
        os.remove(tmp)
    if reemplazar == "1":
        for fn in list(os.listdir(CARPETA)):
            if fn.endswith(f"_{categoria}.txt"):
                os.remove(os.path.join(CARPETA, fn))
                github_borrar(f"datos_bot/{fn}")
    nuevo = datetime.now().strftime("%Y%m%d_%H%M") + "_" + categoria + ".txt"
    cab = f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Vigente hasta: {vigencia or 'sin límite'} ===\n"
    with open(os.path.join(CARPETA, nuevo), "w", encoding="utf-8") as f:
        f.write(cab + texto)
    resp = github_subir(f"datos_bot/{nuevo}", (cab + texto).encode("utf-8"))
    return {"estado": f"✅ Guardado como {nuevo}. {resp}"}

@app.post("/api/delete")
async def api_delete(req: Request):
    d = await req.json()
    if d.get("clave") != CLAVE_ADMIN:
        return {"estado": "❌ Clave incorrecta"}
    nombre = (d.get("nombre") or "").strip()
    ruta = os.path.join(CARPETA, nombre)
    if os.path.exists(ruta):
        os.remove(ruta)
        github_borrar(f"datos_bot/{nombre}")
        return {"estado": f"🗑️ {nombre} eliminado (también del respaldo)."}
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
        os.remove(os.path.join(BASE, "cache.json"))
    except Exception:
        pass
    return {"ok": True}

@app.post("/api/conv/save")
async def conv_save(req: Request):
    d = await req.json()
    cid = re.sub(r"[^a-zA-Z0-9_-]", "", d.get("id", ""))[:40] or "c"
    with open(os.path.join(CONVS, cid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": cid, "user": d.get("user", ""), "titulo": d.get("titulo", "Conversación"), "fecha": datetime.now().isoformat(), "msgs": d.get("msgs", [])}, f, ensure_ascii=False)
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
                out.append({"id": d["id"], "titulo": d.get("titulo", "Conversación"), "fecha": d.get("fecha", "")})
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

@app.get("/api/debug")
async def api_debug():
    out = {"gemini": bool(_sist.cliente_gemini), "groq": bool(_sist.GROQ_KEY), "openrouter": bool(_sist.OR_KEY)}
    try:
        t, l = _sist.responder("Di solo la palabra: listo", [])
        out["respuesta"] = t[:100]
    except Exception as e:
        out["error_texto"] = f"{type(e).__name__}: {e}"
    return out

PAGINA = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UABCBot Idiomas — Facultad de Idiomas de la UABC en Mexicali</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: #eef1f4; }
  .wrap { max-width: 1200px; margin: 0 auto; height: 100vh; display: flex; flex-direction: row; }
  #side { width: 260px; background: #004d38; color: #fff; padding: 14px 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
  #side b { font-size: 14px; }
  #side button { background: rgba(255,255,255,.12); color: #fff; border: none; border-radius: 10px; padding: 9px 10px; text-align: left; cursor: pointer; font-size: 12.5px; }
  #side button:hover { background: rgba(255,255,255,.25); }
  main { flex: 1; display: flex; flex-direction: column; height: 100vh; }
  header { background: linear-gradient(135deg, #00684a, #00855f); color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; border-radius: 0 0 18px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.15); }
  header img { width: 54px; height: 54px; background: #fff; border-radius: 12px; padding: 3px; }
  header h1 { font-size: 17px; } header p { font-size: 12px; opacity: .85; }
  .langs { display: flex; gap: 5px; margin-left: 14px; }
  .langs button { font-size: 11px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: transparent; color: #fff; cursor: pointer; }
  .langs button.on { background: #f7941d; border-color: #f7941d; font-weight: 700; }
  .hbtn { background: rgba(255,255,255,.15); border: none; border-radius: 999px; width: 36px; height: 36px; cursor: pointer; font-size: 16px; }
  #nuevo { margin-left: auto; }
  #chat { flex: 1; overflow-y: auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 82%; display: flex; flex-direction: column; gap: 4px; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.bot { align-self: flex-start; align-items: flex-start; }
  .bub { padding: 10px 14px; border-radius: 16px; font-size: 14.5px; line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,.12); white-space: pre-wrap; }
  .user .bub { background: #d9f6c8; border-bottom-right-radius: 4px; }
  .bot .bub { background: #fff; border-bottom-left-radius: 4px; }
  .msg audio { width: 260px; max-width: 100%; }
  .think .bub { background: #fff; color: #666; font-style: italic; }
  .dots::after { content: ''; animation: pts 1.2s steps(4) infinite; }
  @keyframes pts { 0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; } 75% { content: '...'; } }
  .opts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .opts button { font-size: 12.5px; padding: 7px 11px; border-radius: 999px; border: 1px solid #00855f; background: #f2fbf6; color: #00684a; cursor: pointer; }
  .opts button:hover { background: #00855f; color: #fff; }
  .nota { display: block; margin-top: 9px; font-size: 12px; color: #888; }
  .bar { display: flex; gap: 8px; padding: 10px 12px 14px; align-items: center; }
  #mic { width: 46px; height: 46px; border-radius: 50%; border: none; background: #00684a; color: #fff; font-size: 19px; cursor: pointer; flex-shrink: 0; }
  #mic.rec { background: #d32f2f; animation: pulso 1s infinite; }
  @keyframes pulso { 50% { transform: scale(1.12); } }
  #inp { flex: 1; border: 1px solid #cfd8dc; border-radius: 999px; padding: 12px 18px; font-size: 15px; outline: none; }
  #inp:focus { border-color: #00855f; }
  #send { width: 46px; height: 46px; border-radius: 50%; border: none; background: #f7941d; color: #fff; font-size: 18px; cursor: pointer; flex-shrink: 0; }
  #gear { position: fixed; right: 10px; top: 74px; background: rgba(0,0,0,.25); border: none; color: #fff; border-radius: 50%; width: 30px; height: 30px; cursor: pointer; z-index: 5; }
  #convs { display: none; }
  .drawer { display: none; background: #fff; margin: 0 12px 8px; border-radius: 14px; padding: 12px; box-shadow: 0 2px 10px rgba(0,0,0,.15); font-size: 13px; max-height: 60vh; overflow-y: auto; }
  .drawer input, .drawer select { margin: 4px 0; padding: 8px; border-radius: 8px; border: 1px solid #cfd8dc; width: 100%; }
  .drawer button { margin-top: 6px; padding: 8px 12px; border-radius: 10px; border: none; background: #00684a; color: #fff; cursor: pointer; }
  .drawer .item { display: block; width: 100%; background: #f2f4f7; color: #222; margin: 4px 0; text-align: left; }
  .xbtn { background: #d32f2f !important; float: right; }
  #drop { border: 2px dashed #00855f; border-radius: 12px; padding: 14px; text-align: center; color: #00684a; background: #f2fbf6; margin: 6px 0; cursor: pointer; }
  #dlist { white-space: pre-wrap; background: #f7f9fa; border-radius: 8px; padding: 8px; margin-top: 6px; font-size: 12px; }
  @media (max-width: 900px) { #side { display: none; } #convs { display: block; } }
  @media (min-width: 900px) {
    .bub { font-size: 16.5px; }
    header h1 { font-size: 21px; }
    header p { font-size: 13px; }
    #inp { font-size: 17px; padding: 14px 22px; }
    .msg { max-width: 70%; }
  }
</style>
</head>
<body>
<div class="wrap">
  <aside id="side">
    <b>🗂️ Conversaciones</b>
    <button id="nueva">➕ Nueva conversación</button>
    <div id="lista"></div>
  </aside>
  <main>
    <header>
      <img src="/logo.png" alt="logo">
      <div><h1>UABCBot Idiomas</h1><p>Facultad de Idiomas de la UABC en Mexicali</p></div>
      <div class="langs">
        <button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button>
      </div>
      <button id="convs" class="hbtn" title="Conversaciones">🗂️</button>
      <button id="user" class="hbtn" title="Tu cuenta">👤</button>
      <button id="nuevo" class="hbtn" title="Nueva conversación">🧹</button>
    </header>
    <button id="gear" title="Personal autorizado">⚙️</button>
    <div id="cdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button><b>🗂️ Conversaciones</b><div id="lista2"></div></div>
    <div id="udrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>👤 Tu cuenta</b>
      <div id="who"></div>
      <input id="uusr" placeholder="Usuario o correo">
      <input id="ukey" type="password" placeholder="Clave">
      <button id="ureg">✨ Registrarme</button>
      <button id="ulin">🔑 Entrar</button>
      <button id="uguest">👋 Seguir como invitado</button>
      <button id="uout">🚪 Cerrar sesión</button>
    </div>
    <div id="chat"></div>
    <div id="drawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖ Cerrar</button>
      <b>🛠️ Panel de personal</b>
      <input id="clave" type="password" placeholder="Clave de acceso">
      <button id="unlock">🔓 Entrar</button>
      <button id="salirp">🚪 Salir del panel</button>
      <div id="zona" style="display:none">
        <select id="fcat">
          <option>Avisos</option><option>Suspensiones</option><option>Horarios</option><option>Exámenes</option><option>Convocatorias</option><option>Eventos</option><option>TSU</option><option>PlanDeEstudios</option>
        </select>
        <input id="fvig" type="date">
        <div id="drop">📥 Arrastra aquí tu documento o póster (TXT, PDF o imagen)<br><small>o toca para elegirlo</small></div>
        <input id="ffile" type="file" style="display:none">
        <button id="fsubir">📤 Subir y enseñar al bot</button>
        <button id="nota">🎤 Grabar nota de voz</button>
        <button id="ldocs">🔄 Ver documentos</button>
        <button id="rep">📊 Reporte de uso</button>
        <div id="dlist"></div>
        <input id="fdel" placeholder="Nombre del documento a borrar">
        <button id="bdel">🗑️ Borrar</button>
        <div id="fest"></div>
      </div>
    </div>
    <div class="bar">
      <button id="mic">🎤</button>
      <input id="inp" placeholder="Escribe o dime tu pregunta…">
      <button id="send">➤</button>
    </div>
  </main>
</div>
<script>
let hist = [], state = {pending:false, active:false}, langPref = "auto", rec = null, rec2 = null, chunks = [], currentId = uid(), droppedFile = null;
let currentUser = localStorage.getItem('uabc_user') || "";
const chat = document.getElementById('chat'), inp = document.getElementById('inp');
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function uid(){ return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2,7); }
function bubble(role, text, audio){
  const d = document.createElement('div'); d.className = 'msg ' + role;
  let h = '<div class="bub">' + esc(text) + '</div>';
  if (audio) h += '<audio controls src="' + audio + '"></audio>';
  d.innerHTML = h; chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  return d;
}
async function welcome(){
  let opts = [
    {q:"¿Cuántos créditos necesito para titularme en Traducción?", t:"💳 Créditos para titularme"},
    {q:"¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?", t:"📅 Horarios del CEC"},
    {q:"¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?", t:"🎓 Requisitos de admisión"},
    {q:"¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?", t:"🏛️ Carreras y TSU"}
  ];
  try {
    const d = await (await fetch('/api/topfaq')).json();
    if (d && d.length) opts = d.map(x => ({q: x.q, t: "🔥 " + (x.q.length > 40 ? x.q.slice(0,40) + "…" : x.q)}));
  } catch(e) {}
  const d = document.createElement('div'); d.className = 'msg bot';
  d.innerHTML = '<div class="bub">👋 ¡Hola! Soy <b>UABCBot Idiomas</b>, el asistente de la Facultad de Idiomas de la UABC en Mexicali. Toca una opción o escribe/dime tu pregunta en español, inglés o francés.<div class="opts">'
    + opts.map(o => '<button data-q="' + esc(o.q) + '">' + esc(o.t) + '</button>').join('')
    + '</div><span class="nota">Personal docente: escribe o di "administración".</span></div>';
  chat.appendChild(d);
  d.querySelectorAll('[data-q]').forEach(b => b.onclick = () => send(b.dataset.q));
  chat.scrollTop = chat.scrollHeight;
}
function thinking(){
  removeThink();
  const d = document.createElement('div'); d.className = 'msg bot think'; d.id = 'think';
  d.innerHTML = '<div class="bub">🤔 Trabajando en tu respuesta<span class="dots"></span></div>';
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
}
function removeThink(){ const t = document.getElementById('think'); if (t) t.remove(); }
function refreshWho(){
  document.getElementById('who').innerText = currentUser ? '✅ Sesión: ' + currentUser + ' (tus conversaciones se guardan)' : '👋 Modo invitado: sin memoria de conversaciones.';
}
function saveConv(){
  if (!currentUser) return;
  const titulo = ((hist.find(m => m.role === 'user') || {}).content || 'Nueva conversación').slice(0, 40);
  fetch('/api/conv/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: currentId, user: currentUser, titulo, msgs: hist})}).then(() => loadList());
}
async function loadList(){
  if (!currentUser) {
    const msg = '<small>👋 Invitado: sin memoria. Regístrate con 👤 para guardar tus conversaciones.</small>';
    document.getElementById('lista').innerHTML = msg;
    document.getElementById('lista2').innerHTML = msg;
    return;
  }
  const d = await (await fetch('/api/conv/list?user=' + encodeURIComponent(currentUser))).json();
  const html = d.map(c => '<button class="item" data-id="' + c.id + '">' + esc(c.titulo) + '</button>').join('');
  document.getElementById('lista').innerHTML = html || '<small>Sin conversaciones aún.</small>';
  document.getElementById('lista2').innerHTML = html || '<small>Sin conversaciones aún.</small>';
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
  hist.push({role:'user', content: esClave ? '••••••' : msg});
  if (esClave) setTimeout(() => { el.querySelector('.bub').textContent = '🔑 ••••••'; }, 30000);
  inp.value = '';
  thinking();
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg, hist: hist.slice(-7), state, lang: langPref})});
  const d = await r.json(); removeThink(); state = d.state;
  hist.push({role:'assistant', content: d.reply, audio: d.audio}); bubble('bot', d.reply, d.audio);
  saveConv();
}
async function loadDocs(){
  const d = await (await fetch('/api/docs')).json();
  document.getElementById('dlist').innerText = (d.docs || []).join('\\n') || 'Sin documentos.';
}
document.getElementById('send').onclick = () => send(inp.value);
inp.onkeydown = e => { if (e.key === 'Enter') send(inp.value); };
document.getElementById('nuevo').onclick = nueva;
document.getElementById('nueva').onclick = nueva;
document.getElementById('convs').onclick = () => { const d = document.getElementById('cdrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; loadList(); };
document.getElementById('user').onclick = () => { const d = document.getElementById('udrawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; refreshWho(); };
document.getElementById('ureg').onclick = async () => {
  const d = await (await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) return alert(d.error);
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
};
document.getElementById('ulin').onclick = async () => {
  const d = await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({usuario: document.getElementById('uusr').value, clave: document.getElementById('ukey').value})})).json();
  if (!d.ok) return alert(d.error);
  currentUser = d.usuario; localStorage.setItem('uabc_user', currentUser);
  refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none';
};
document.getElementById('uguest').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; };
document.getElementById('uout').onclick = () => { currentUser = ""; localStorage.removeItem('uabc_user'); refreshWho(); loadList(); document.getElementById('udrawer').style.display = 'none'; };
[['Lauto','auto'],['Les','es'],['Len','en'],['Lfr','fr']].forEach(([id, v]) => {
  document.getElementById(id).onclick = e => { langPref = v; document.querySelectorAll('.langs button').forEach(x => x.classList.remove('on')); e.target.classList.add('on'); };
});
const drop = document.getElementById('drop');
drop.onclick = () => document.getElementById('ffile').click();
drop.ondragover = e => e.preventDefault();
drop.ondrop = e => { e.preventDefault(); if (e.dataTransfer.files[0]) { droppedFile = e.dataTransfer.files[0]; drop.innerHTML = '📎 ' + esc(droppedFile.name); } };
document.getElementById('ffile').onchange = e => { droppedFile = e.target.files[0] || null; if (droppedFile) drop.innerHTML = '📎 ' + esc(droppedFile.name); };
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
    if (d.texto) { bubble('user', '🎤 ' + d.texto); hist.push({role:'user', content: d.texto}); }
    if (d.reply) { bubble('bot', d.reply, d.audio); hist.push({role:'assistant', content: d.reply, audio: d.audio}); }
    saveConv();
  };
  rec.start(); mic.classList.add('rec');
};
document.getElementById('gear').onclick = () => { const d = document.getElementById('drawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; };
document.getElementById('salirp').onclick = () => { state = {pending:false, active:false}; document.getElementById('drawer').style.display = 'none'; document.getElementById('zona').style.display = 'none'; };
document.getElementById('unlock').onclick = async () => {
  const r = await fetch('/api/unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})});
  const d = await r.json();
  document.getElementById('zona').style.display = d.ok ? 'block' : 'none';
  if (d.ok) loadDocs();
  if (!d.ok) alert('❌ Clave incorrecta');
};
document.getElementById('fsubir').onclick = async () => {
  const f = document.getElementById('ffile').files[0] || droppedFile;
  if (!f) return alert('Selecciona o arrastra un archivo');
  const fd = new FormData();
  fd.append('archivo', f);
  fd.append('categoria', document.getElementById('fcat').value);
  fd.append('vigencia', document.getElementById('fvig').value);
  fd.append('reemplazar', '0');
  const d = await (await fetch('/api/upload', {method:'POST', body: fd})).json();
  document.getElementById('fest').innerText = d.estado;
  loadDocs();
};
document.getElementById('ldocs').onclick = loadDocs;
document.getElementById('bdel').onclick = async () => {
  const d = await (await fetch('/api/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value, nombre: document.getElementById('fdel').value})})).json();
  document.getElementById('fest').innerText = d.estado; loadDocs();
};
document.getElementById('nota').onclick = async () => {
  if (rec2 && rec2.state === 'recording') { rec2.stop(); return; }
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  let ch = []; rec2 = new MediaRecorder(stream);
  rec2.ondataavailable = e => ch.push(e.data);
  rec2.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    const fd = new FormData();
    fd.append('audio', new Blob(ch, {type:'audio/webm'}), 'nota.webm');
    fd.append('categoria', document.getElementById('fcat').value);
    const d = await (await fetch('/api/voice_note', {method:'POST', body: fd})).json();
    document.getElementById('fest').innerText = d.estado;
    loadDocs();
  };
  rec2.start();
  document.getElementById('fest').innerText = '🔴 Grabando nota… toca de nuevo para terminar.';
};
document.getElementById('rep').onclick = async () => {
  const d = await (await fetch('/api/report', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})})).json();
  if (d.error) return alert(d.error);
  document.getElementById('fest').innerText = '📊 Total: ' + d.total + ' · Hoy: ' + d.hoy + ' · Idiomas: ' + JSON.stringify(d.idiomas)
    + '\\n\\n🔥 Más frecuentes:\\n' + d.top.map((x, i) => (i+1) + '. ' + x[0] + ' (' + x[1] + ')').join('\\n');
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
