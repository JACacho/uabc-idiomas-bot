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
  main { flex: 1; display:
