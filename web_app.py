import os
import re
import uuid
import base64
import asyncio
import requests as http_requests
from datetime import datetime
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
from sistema import responder, transcribir, generar_voz

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE, "datos_bot")
AUDIOS = os.path.join(BASE, "audios")
CONTADOR = os.path.join(BASE, "conteo.txt")
CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "fimxl2026")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPO", "")
LOGO = os.path.join(BASE, "logo.png")
LOGO_URL = "https://raw.githubusercontent.com/JACacho/uabc-idiomas-bot/main/logo.png"
os.makedirs(AUDIOS, exist_ok=True)
os.makedirs(CARPETA, exist_ok=True)

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

def normalizar_faq(texto):
    t = texto.lower()
    for claves, canonica in FAQ:
        if any(k in t for k in claves) and len(t) < 90:
            return canonica
    return texto

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
            return "✅ Acceso concedido, profe. Escribe tu aviso tal cual y lo publico al instante. Escribe SALIR para cerrar.", None, state
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
    sumar_pregunta()
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

@app.post("/api/chat")
async def api_chat(req: Request):
    d = await req.json()
    try:
        respuesta, lang, state = router(d.get("msg"), d.get("hist"), d.get("state"), d.get("lang", "auto"))
        audio = await producir_audio(respuesta, lang)
    except Exception as e:
        respuesta = f"⚠️ Error interno: {type(e).__name__}: {e}"
        audio = None
        state = d.get("state") or {}
    return {"reply": respuesta, "audio": audio, "state": state}

@app.post("/api/voice")
async def api_voice(audio: UploadFile = File(...), hist: str = Form("[]"), state: str = Form("{}"), lang: str = Form("auto")):
    data = await audio.read()
    texto, _ = transcribir(data)
    if not texto:
        return {"texto": "", "reply": "⚠️ No logré escuchar bien. Intenta de nuevo más cerca del micrófono.", "audio": None, "state": state}
    import json as _json
    respuesta, lang2, state2 = router(texto, _json.loads(hist), _json.loads(state), lang)
    aud = await producir_audio(respuesta, lang2)
    return {"texto": texto, "reply": respuesta, "audio": aud, "state": state2}

@app.post("/api/unlock")
async def api_unlock(req: Request):
    d = await req.json()
    return {"ok": d.get("clave") == CLAVE_ADMIN}

@app.post("/api/upload")
async def api_upload(archivo: UploadFile = File(...), categoria: str = Form("Avisos"), vigencia: str = Form(""), reemplazar: str = Form("1")):
    nombre_orig = archivo.name or "doc.txt"
    tmp = os.path.join(BASE, "tmp_" + nombre_orig)
    with open(tmp, "wb") as f:
        f.write(await archivo.read())
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

@app.get("/api/docs")
async def api_docs():
    archivos = [f for f in sorted(os.listdir(CARPETA)) if f.endswith(".txt")]
    return {"docs": archivos}

@app.get("/audio/{nombre}")
async def audio(nombre: str):
    return FileResponse(os.path.join(AUDIOS, nombre), media_type="audio/mpeg")

@app.get("/logo.png")
async def logo():
    if os.path.exists(LOGO):
        return FileResponse(LOGO)
    return JSONResponse({})

import sistema as _sist

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
  .wrap { max-width: 960px; margin: 0 auto; height: 100vh; display: flex; flex-direction: column; }
  header { background: linear-gradient(135deg, #00684a, #00855f); color: #fff; padding: 12px 16px; display: flex; align-items: center; gap: 12px; border-radius: 0 0 18px 18px; box-shadow: 0 2px 10px rgba(0,0,0,.15); }
  header img { width: 54px; height: 54px; background: #fff; border-radius: 12px; padding: 3px; }
  header h1 { font-size: 17px; } header p { font-size: 12px; opacity: .85; }
  .langs { display: flex; gap: 5px; margin-left: 14px; }
  .langs button { font-size: 11px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.5); background: transparent; color: #fff; cursor: pointer; }
  .langs button.on { background: #f7941d; border-color: #f7941d; font-weight: 700; }
  .hbtn { margin-left: auto; background: rgba(255,255,255,.15); border: none; border-radius: 999px; width: 36px; height: 36px; cursor: pointer; font-size: 16px; }
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
  #gear { position: fixed; right: 10px; top: 74px; background: rgba(0,0,0,.25); border: none; color: #fff; border-radius: 50%; width: 30px; height: 30px; cursor: pointer; }
  #drawer { display: none; background: #fff; margin: 0 12px 8px; border-radius: 14px; padding: 12px; box-shadow: 0 2px 10px rgba(0,0,0,.15); font-size: 13px; }
  #drawer input, #drawer select { margin: 4px 0; padding: 8px; border-radius: 8px; border: 1px solid #cfd8dc; width: 100%; }
  #drawer button { margin-top: 6px; padding: 8px 12px; border-radius: 10px; border: none; background: #00684a; color: #fff; cursor: pointer; }
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
  <header>
    <img src="/logo.png" alt="logo">
    <div><h1>UABCBot Idiomas</h1><p>Facultad de Idiomas de la UABC en Mexicali · es · en · fr</p></div>
    <div class="langs">
      <button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button>
    </div>
    <button id="nuevo" class="hbtn" title="Nueva conversación">🧹</button>
  </header>
  <button id="gear" title="Personal autorizado">⚙️</button>
  <div id="chat"></div>
  <div id="drawer">
    <b>🛠️ Panel de personal</b>
    <input id="clave" type="password" placeholder="Clave de acceso">
    <button id="unlock">🔓 Entrar</button>
    <div id="zona" style="display:none">
      <input id="fcat" placeholder="Categoría (Avisos, Horarios, TSU...)">
      <input id="fvig" placeholder="Vigente hasta (dd/mm/aaaa)">
      <input id="ffile" type="file">
      <button id="fsubir">📤 Subir y enseñar al bot</button>
      <div id="fest"></div>
    </div>
  </div>
  <div class="bar">
    <button id="mic">🎤</button>
    <input id="inp" placeholder="Escribe o dime tu pregunta…">
    <button id="send">➤</button>
  </div>
</div>
<script>
let hist = [], state = {pending:false, active:false}, langPref = "auto", rec = null, chunks = [];
const chat = document.getElementById('chat'), inp = document.getElementById('inp');
const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function bubble(role, text, audio){
  const d = document.createElement('div'); d.className = 'msg ' + role;
  let h = '<div class="bub">' + esc(text) + '</div>';
  if (audio) h += '<audio controls src="' + audio + '"></audio>';
  d.innerHTML = h; chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
}
function welcome(){
  const d = document.createElement('div'); d.className = 'msg bot';
  d.innerHTML = '<div class="bub">👋 ¡Hola! Soy <b>UABCBot Idiomas</b>, el asistente de la Facultad de Idiomas de la UABC en Mexicali. Toca una opción o escribe/dime tu pregunta en español, inglés o francés.'
    + '<div class="opts">'
    + '<button data-q="¿Cuántos créditos necesito para titularme en Traducción?">💳 Créditos para titularme</button>'
    + '<button data-q="¿Cuáles son los horarios del Centro de Enseñanza de Lenguas (CEC)?">📅 Horarios del CEC</button>'
    + '<button data-q="¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?">🎓 Requisitos de admisión</button>'
    + '<button data-q="¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?">🏛️ Carreras y TSU</button>'
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
welcome();
async function send(msg){
  if (!msg.trim()) return;
  bubble('user', msg); hist.push({role:'user', content: msg}); inp.value = '';
  thinking();
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg, hist: hist.slice(-7), state, lang: langPref})});
  const d = await r.json(); removeThink(); state = d.state;
  hist.push({role:'assistant', content: d.reply}); bubble('bot', d.reply, d.audio);
}
document.getElementById('send').onclick = () => send(inp.value);
inp.onkeydown = e => { if (e.key === 'Enter') send(inp.value); };
document.getElementById('nuevo').onclick = () => { hist = []; state = {pending:false, active:false}; chat.innerHTML = ''; welcome(); };
[['Lauto','auto'],['Les','es'],['Len','en'],['Lfr','fr']].forEach(([id, v]) => {
  document.getElementById(id).onclick = e => { langPref = v; document.querySelectorAll('.langs button').forEach(x => x.classList.remove('on')); e.target.classList.add('on'); };
});
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
    if (d.reply) { bubble('bot', d.reply, d.audio); hist.push({role:'assistant', content: d.reply}); }
  };
  rec.start(); mic.classList.add('rec');
};
document.getElementById('gear').onclick = () => { const d = document.getElementById('drawer'); d.style.display = d.style.display === 'block' ? 'none' : 'block'; };
document.getElementById('unlock').onclick = async () => {
  const r = await fetch('/api/unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({clave: document.getElementById('clave').value})});
  const d = await r.json();
  document.getElementById('zona').style.display = d.ok ? 'block' : 'none';
  if (!d.ok) alert('❌ Clave incorrecta');
};
document.getElementById('fsubir').onclick = async () => {
  const f = document.getElementById('ffile').files[0]; if (!f) return alert('Selecciona un archivo');
  const fd = new FormData();
  fd.append('archivo', f);
  fd.append('categoria', document.getElementById('fcat').value || 'Avisos');
  fd.append('vigencia', document.getElementById('fvig').value);
  fd.append('reemplazar', '1');
  const d = await (await fetch('/api/upload', {method:'POST', body: fd})).json();
  document.getElementById('fest').innerText = d.estado;
};
</script>
</body>
</html>
"""

@app.get("/")
async def inicio():
    return HTMLResponse(PAGINA)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
