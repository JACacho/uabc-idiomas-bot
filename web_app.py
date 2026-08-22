import os, re, uuid, json, time, base64, hashlib, secrets, tempfile, requests
from datetime import datetime, date, timedelta
from collections import Counter
from google import genai as genai_lib
from google.genai import types as gtypes
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn

VERSION = "v17-2026-08-22"
BASE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(BASE, "Manual_Aspirantes_Idiomas_UABC.txt")
CARPETA = os.path.join(BASE, "datos_bot")
AUDIOS = os.path.join(BASE, "audios"); IMGS = os.path.join(BASE, "posters")
CAPTURAS = os.path.join(BASE, "capturas"); CONVS = os.path.join(BASE, "conversaciones")
FEEDBACK = os.path.join(BASE, "feedback")
CACHE = os.path.join(BASE, "cache.json"); USO = os.path.join(BASE, "uso.jsonl")
USERS = os.path.join(BASE, "users.json"); TOPFAQ_CACHE = os.path.join(BASE, "topfaq_cache.json")
RESPONSABLES = os.path.join(BASE, "responsables.json"); DOCS_META = os.path.join(BASE, "docs_meta.json")
CATALOGO = os.path.join(BASE, "catalogo.json")
CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "fimxl2026")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", ""); GH_REPO = os.environ.get("GITHUB_REPO", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", ""); GEMINI_KEY_2 = os.environ.get("GEMINI_API_KEY_2", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", ""); OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"; GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TOPFAQ_HOURS = float(os.environ.get("TOPFAQ_HOURS", "48"))
LOGO = os.path.join(BASE, "logo.png"); LOGO_URL = "https://raw.githubusercontent.com/JACacho/uabc-idiomas-bot/main/logo.png"
for d in (AUDIOS, CARPETA, CONVS, IMGS, FEEDBACK, CAPTURAS): os.makedirs(d, exist_ok=True)
CATS_INTERNAS = ("clases", "tareas", "internos")

def _mk_client(k):
    if not k: return None
    try: return genai_lib.Client(api_key=k)
    except Exception: return None
cliente_gemini = _mk_client(GEMINI_KEY); cliente_gemini2 = _mk_client(GEMINI_KEY_2)

AREAS_RESP = {"Admisión":"admision.mxl@uabc.edu.mx","CEC":"recepcionmxl@uabc.edu.mx","Escolar/Escolaridad":"escolares_idiomas_mxl@uabc.edu.mx","Egresados/Bolsa de trabajo":"egresados__idiomas__mxl@uabc.edu.mx","Eventos":"idiomas.mxl@uabc.edu.mx","Otro":"idiomas.mxl@uabc.edu.mx"}

CAT_DEF = [
 {"tema":"Doctorado / Posgrado (DCL)","kw":["doctorado","doctorados","dcl","posgrado","doctor"],"nombre":"Dr. Maldonado","rol":"Responsable de Doctorados","correo":"","tel":"686-689-0825","oficina":"","horario":""},
 {"tema":"Titulación","kw":["titulacion","titulación","titularme","titular"],"nombre":"Responsable de Titulación","rol":"Titulación","correo":"","tel":"686-689-0825","oficina":"","horario":""},
 {"tema":"CEC / Cursos de idiomas","kw":["cec","curso","cursos","ingles","inglés","frances","francés"],"nombre":"Responsable CEC","rol":"Centro de Enseñanza de Lenguas","correo":"recepcionmxl@uabc.edu.mx","tel":"686 841-82-91 ext. 300","oficina":"","horario":""},
 {"tema":"Egresados / Bolsa de trabajo","kw":["egresado","egresados","bolsa","empleo"],"nombre":"Mtra. Dulce Rodríguez Díaz","rol":"Responsable de Egresados y Bolsa de Trabajo","correo":"egresados__idiomas__mxl@uabc.edu.mx","tel":"686-689-0825","oficina":"","horario":""},
]
def cargar_catalogo():
    try: cat = _jload(CATALOGO, [])
    except Exception: cat = []
    return cat + list(CAT_DEF)
def resp_catalogo(e):
    s = f"Sobre {e['tema']}, te atiende directamente {e['nombre']}" + (f" ({e['rol']})" if e.get('rol') else "") + "."
    c = []
    if e.get('correo'): c.append("correo " + e['correo'])
    if e.get('tel'): c.append("tel. " + e['tel'])
    if e.get('oficina'): c.append("oficina " + e['oficina'])
    if e.get('horario'): c.append("horario " + e['horario'])
    if c: s += " Contacto directo: " + ", ".join(c) + "."
    else: s += f" Si llamas al 686-689-0825 pide que te canalicen directamente con {e['nombre']}; así no das vueltas."
    return s

try:
    if not os.path.exists(LOGO):
        r = requests.get(LOGO_URL, timeout=10)
        if r.status_code == 200 and r.content: open(LOGO, "wb").write(r.content)
except Exception: pass

VOCES = {"es":"es-MX-DaliaNeural","en":"en-US-AriaNeural","fr":"fr-FR-DeniseNeural"}
DIAS = {0:"lunes",1:"martes",2:"miércoles",3:"jueves",4:"viernes",5:"sábado",6:"domingo"}
MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
MESES_INV = {v:k for k,v in MESES.items()}
MESES_ALT = "(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
EXT_IMG = (".png",".jpg",".jpeg",".webp")
PROMPT_POSTER = "Este es un anuncio o póster institucional. Extrae TODA la información útil (qué evento, quién invita, fecha, hora, lugar, contacto, requisitos) y devuélvela como texto claro en español, sin comentarios."
IMG_PRUEBA = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

def fecha_hoy_es():
    n = datetime.now(); return f"{DIAS[n.weekday()]} {n.day} de {MESES[n.month]} de {n.year}"
def detectar_idioma(t):
    t = (t or "").lower()
    fr = ["bonjour","merci","combien","pour","avec","vous","diplôm","traduction","salut","crédit","je ","étud","etud","français","francais","voud","veux","voaux","quel","quelle","aime","les ","des ","anglais"]
    en = ["hello","thank","how","many","credit","degree","translation","what","when","where","i ","would","like","to ","study","french","english","do ","you","for","me","is ","are ","the ","my ","can","help"]
    hf = sum(1 for w in fr if w in t); he = sum(1 for w in en if w in t)
    if hf >= 2 and hf > he: return "fr"
    if he >= 2 and he > hf: return "en"
    return "es"
def _fechas_doc(t):
    f = []; t = (t or "").lower()
    for d,m,y in re.findall(r"(\d{1,2})\s+de\s+"+MESES_ALT+r"\s+de\s+(\d{4})", t):
        try: f.append(date(int(y), MESES_INV[m], int(d)))
        except Exception: pass
    for d,m in re.findall(r"(\d{1,2})\s+de\s+"+MESES_ALT, t):
        try: f.append(date(date.today().year, MESES_INV[m], int(d)))
        except Exception: pass
    for d,m,y in re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", t):
        try: f.append(date(int(y), int(m), int(d)))
        except Exception: pass
    return f

MEMORIA_OFICIAL = [
 (["credito","titular","credit"], {"es":"Para titularte en la Licenciatura en Traducción (LT) necesitas 349 créditos: 237 obligatorios, 102 optativos y 10 de prácticas. Detalles: idiomas.mxl.uabc.mx o 686-689-0825.","en":"To graduate from Translation (LT) you need 349 credits. Details: idiomas.mxl.uabc.mx or 686-689-0825.","fr":"Pour diplômer en Traduction (LT) il faut 349 crédits. Détails: idiomas.mxl.uabc.mx ou 686-689-0825."}),
 (["carrera","tsu","tecnico","técnico","programas","traduc","translation","traduction"], {"es":"La Facultad ofrece Licenciaturas en Enseñanza de Lenguas (LEL) y Traducción (LT), y el TSU. Consulta idiomas.mxl.uabc.mx o 686-689-0825.","en":"The Faculty offers Language Teaching (LEL) and Translation (LT) degrees plus a TSU. See idiomas.mxl.uabc.mx.","fr":"La Faculté offre les licences LEL et LT et un TSU. Voir idiomas.mxl.uabc.mx."}),
 (["frances","francés","french","français","francais","ingles","inglés","english","anglais","study","estudiar","etud","curso","cours","cec","horario"], {"es":"El CEC ofrece cursos de inglés, francés, alemán, italiano, portugués, ruso, mandarín, japonés, coreano y español, en formatos semanal, sabatino, intensivo e intersemestral. Grupos en cecuabc.com. Informes: recepcionmxl@uabc.edu.mx o 686 841-82-91 ext. 300.","en":"The CEC offers English, French, German, Italian, Portuguese, Russian, Mandarin, Japanese, Korean and Spanish courses. Groups at cecuabc.com.","fr":"Le CEC propose des cours d'anglais, français, allemand, italien, portugais, russe, mandarin, japonais, coréen et espagnol. Groupes sur cecuabc.com."}),
 (["admision","requisito","admission"], {"es":"Para ingresar: 1) concluir bachillerato, 2) certificado/acta/CURP, 3) registro en el portal (agosto y enero), 4) Examen de Selección. No se requiere inglés avanzado. Fechas: admision.uabc.mx.","en":"To enter: finish high school, certificates, register (Aug/Jan), take the Selection Exam. No advanced English needed. Dates: admision.uabc.mx.","fr":"Pour entrer: terminer le lycée, certificats, s'inscrire (août/janvier), passer l'Examen. Dates: admision.uabc.mx."}),
 (["que haces","what do you do","ayudar","help","sirves","puedes hacer"], {"es":"Te informo sobre créditos, CEC, admisión, carreras, avisos y a QUIÉN acudir por cada tema, en español, inglés o francés: te leo o te escucho.","en":"I cover credits, CEC, admission, degrees, notices and WHO to contact for each topic: I read you or listen to you.","fr":"Je couvre crédits, CEC, admission, licences, avis et QUI contacter : je te lis ou je t'écoute."}),
]

def _limpiar_doc(t):
    out = []
    for ln in (t or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("===") or s.startswith("DOCUMENTO") or s.startswith("🖼️"): continue
        out.append(s)
    return "\n".join(out)
def _tokens(t): return set(re.findall(r"[a-záéíóúñü$0-9]+", (t or "").lower()))
def _es_valida(t): return bool(t) and not (t.strip().endswith("?") and len(t) < 160)
def _es_interno_doc(fn):
    low = fn.lower(); return any(f"_{c}" in low for c in CATS_INTERNAS)
def _cargar_docs(rol="externo"):
    docs = {}
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                if rol != "interno" and _es_interno_doc(fn): continue
                try: docs[fn] = _limpiar_doc(open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore").read())
                except Exception: pass
    return docs
def cargar_contexto(preg, rol="externo"):
    partes = []
    try: partes.append(_limpiar_doc(open(MANUAL, encoding="utf-8", errors="ignore").read()))
    except Exception: pass
    docs = _cargar_docs(rol); hoy = date.today(); hor = hoy + timedelta(days=14)
    rec = sorted(docs.keys(), reverse=True)[:2]
    fres = [fn for fn, t in docs.items() if any(hoy <= f <= hor for f in _fechas_doc(t))][:3]
    qt = _tokens(preg)
    sc = sorted(((len(qt & _tokens(t)), fn) for fn, t in docs.items()), reverse=True)
    sel = []
    for fn in rec + fres + [f for _, f in sc[:2]]:
        if fn not in sel: sel.append(fn)
    for fn in sel[:5]: partes.append(docs[fn])
    return "\n\n".join(partes)[:12000]
def respuesta_de_documentos(preg, rol="externo"):
    docs = _cargar_docs(rol)
    if not docs: return ""
    hoy = date.today(); hor = hoy + timedelta(days=14); p = (preg or "").lower()
    if any(k in p for k in ("semana","evento","hoy","mañana","pronto","avisos","hay")):
        fres = [t for t in docs.values() if any(hoy <= f <= hor for f in _fechas_doc(t))][:2]
        if fres: return "📅 Avisos oficiales recientes:\n\n" + "\n\n".join(t[:500] for t in fres)
    qt = _tokens(preg)
    sc = sorted(((len(qt & _tokens(t)), t) for t in docs.values()), reverse=True)
    if sc and sc[0][0] >= 3: return "Según la información oficial: " + sc[0][1][:600]
    return ""
def sistema_prompt(ctx, rol="externo"):
    extra = " El usuario es comunidad UABC: puedes incluir avisos internos de clases/tareas. " if rol == "interno" else " El usuario es público general: NO reveles info interna de clases/tareas. "
    return (f"Hoy es {fecha_hoy_es()}. Eres UABCBot Idiomas de la Facultad de Idiomas UABC Mexicali. "
      "Responde en el idioma de la pregunta, MÁXIMO 3-4 oraciones. Sé ultra-conciso. Si preguntan COSTOS da la cifra exacta disponible. "
      "NUNCA repitas la pregunta. FECHAS: primero eventos de los próximos 14 días. "
      "REGLAS: responde solo lo preguntado; no copies nombres de archivo ni ===; reformula. "
      "Si un tema tiene responsable, menciónalo para atender directo sin trámites. "
      "Si no aparece, sugiere 686-689-0825 / idiomas.mxl@uabc.edu.mx. " + extra + f"\nINFORMACIÓN:\n{ctx}")

def llamar_gemini(cl, sp, hist, preg):
    if not cl: return None
    try:
        c = [{"role": "user" if m["role"]=="user" else "model", "parts":[{"text":m["content"]}]} for m in hist]
        c.append({"role":"user","parts":[{"text":preg}]})
        r = cl.models.generate_content(model="gemini-2.5-flash", contents=c, config={"system_instruction":sp,"temperature":0.1})
        return (r.text or "").strip() or None
    except Exception: return None
def llamar_openai(sp, hist, preg, url, key, mods):
    if not key: return None
    for m in mods:
        try:
            msgs = [{"role":"system","content":sp}] + hist + [{"role":"user","content":preg}]
            r = requests.post(url, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, json={"model":m,"messages":msgs,"temperature":0.1}, timeout=15)
            t = (r.json()["choices"][0]["message"]["content"] or "").strip()
            if t: return t
        except Exception: continue
    return ""
def llamar_vision(url,key,mods,b64,mime,prompt):
    if not key: return ""
    for m in mods:
        try:
            msgs=[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}}]}]
            r=requests.post(url,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":m,"messages":msgs,"temperature":0.1},timeout=30)
            t=(r.json()["choices"][0]["message"]["content"] or "").strip()
            if t: return t
        except Exception: continue
    return ""
def _vision_gemini(cl,data,mime,prompt):
    if not cl: return ""
    for m in ("gemini-2.5-flash","gemini-2.0-flash","gemini-2.5-flash-lite"):
        try:
            r=cl.models.generate_content(model=m,contents=[gtypes.Part(inline_data=gtypes.Blob(data=data,mime_type=mime)),prompt])
            t=(r.text or "").strip()
            if t: return t
        except Exception: continue
    return ""
def extraer_imagen(data,mime="image/jpeg"):
    errs=[]
    for i,c in enumerate((cliente_gemini,cliente_gemini2),1):
        t=_vision_gemini(c,data,mime,PROMPT_POSTER)
        if t: return t,""
        errs.append(f"Gemini{i} sin cuota")
    b64=base64.b64encode(data).decode()
    t=llamar_vision(GROQ_URL,GROQ_KEY,["llama-3.2-90b-vision-preview"],b64,mime,PROMPT_POSTER)
    if t: return t,""
    errs.append("Groq visión no disp.")
    t=llamar_vision(OR_URL,OR_KEY,["meta-llama/llama-3.2-90b-vision-instruct:free"],b64,mime,PROMPT_POSTER)
    if t: return t,""
    errs.append("OpenRouter visión no disp.")
    return ""," | ".join(errs)

def _jload(p,d={}):
    try: return json.load(open(p,encoding="utf-8"))
    except Exception: return d
def _jdump(p,d):
    try: json.dump(d,open(p,"w",encoding="utf-8"),ensure_ascii=False)
    except Exception: pass
def _cargar_cache():
    try: return json.load(open(CACHE,encoding="utf-8"))
    except Exception: return {}
def _guardar_cache(c):
    try: json.dump(c,open(CACHE,"w",encoding="utf-8"),ensure_ascii=False)
    except Exception: pass
def _es_cacheable(t):
    low=(t or "").lower()
    return not (t.startswith("⚠️") or t.startswith("📅") or t.startswith("Según la información oficial") or t.startswith("Sobre ") or len(t)<60 or "ayudarte hoy" in low or "no está en el contexto" in low or "===" in t or "documento " in low or len(t)>900)
def _hash(c,s): return hashlib.sha256((s+c).encode()).hexdigest()

def responder(pregunta, historial, lang_pref="auto", rol="externo"):
    p=(pregunta or "").lower()
    lang = lang_pref if lang_pref in ("es","en","fr") else detectar_idioma(pregunta)
    for e in cargar_catalogo():
        if any(k in p for k in e["kw"]):
            return resp_catalogo(e), lang
    if not any(k in p for k in ("cuanto","cuánto","cuesta","costo","precio","inscri")):
        for claves,trad in MEMORIA_OFICIAL:
            if any(k in p for k in claves): return trad.get(lang,trad["es"]),lang
    clave=p.strip()[:120]+f"|{rol}"
    cache=_cargar_cache()
    if clave in cache: return cache[clave][0],cache[clave][1]
    sp=sistema_prompt(cargar_contexto(pregunta,rol),rol)
    suf={"es":" (Responde en español, conciso.)","en":" (Answer in English, concise.)","fr":" (Réponds en français, concis.)"}[lang]
    pf=pregunta+suf
    hist=[{"role":("user" if m["role"]=="user" else "assistant"),"content":m["content"]} for m in (historial or []) if isinstance(m,dict) and isinstance(m.get("content"),str)]
    # Primero Groq (gratis), luego Gemini (gratis), último OpenRouter (pago)
    texto=llamar_openai(sp,hist,pf,GROQ_URL,GROQ_KEY,["llama-3.1-70b-versatile","llama-3.1-8b-instant"])
    if not _es_valida(texto): texto=llamar_gemini(cliente_gemini,sp,hist,pf)
    if not _es_valida(texto): texto=llamar_openai(sp,hist,pf,OR_URL,OR_KEY,["deepseek/deepseek-v4-flash"])
    if not _es_valida(texto): texto=llamar_gemini(cliente_gemini,sp,hist,pf)
    if not _es_valida(texto): texto=llamar_gemini(cliente_gemini2,sp,hist,pf)
    if not _es_valida(texto): texto=llamar_openai(sp,hist,pf,GROQ_URL,GROQ_KEY,["llama-3.3-70b-versatile"])
    if not _es_valida(texto):
        fb=respuesta_de_documentos(pregunta,rol)
        if fb: return fb,lang
    if not _es_valida(texto): texto="⚠️ Motores saturados. Intenta en unos segundos."
    texto=re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+","",texto).strip()
    if _es_cacheable(texto): cache[clave]=[texto,lang]; _guardar_cache(cache)
    return texto,lang

def transcribir_groq(data):
    if not GROQ_KEY: return ""
    try:
        r=requests.post(GROQ_URL.replace("/chat/completions","/audio/transcriptions"),headers={"Authorization":f"Bearer {GROQ_KEY}"},files={"file":("voz.webm",data,"audio/webm")},data={"model":"whisper-large-v3"},timeout=60)
        return (r.json().get("text") or "").strip()
    except Exception: return ""
def transcribir(ab):
    for c in (cliente_gemini,cliente_gemini2):
        if not c: continue
        for mime in ("audio/webm","audio/wav","audio/mp3","audio/ogg"):
            try:
                r=c.models.generate_content(model="gemini-2.5-flash",contents=[gtypes.Part(inline_data=gtypes.Blob(data=ab,mime_type=mime)),"Transcribe este audio (es/en/fr). Solo la transcripción."])
                t=(r.text or "").strip()
                if t: return t,detectar_idioma(t)
            except Exception: continue
    t=transcribir_groq(ab)
    return (t,detectar_idioma(t)) if t else ("","es")
async def generar_voz(texto,lang):
    try:
        import edge_tts
        ruta=os.path.join(tempfile.gettempdir(),"respuesta_uabc.mp3")
        await edge_tts.Communicate(texto,VOCES.get(lang,VOCES["es"])).save(ruta)
        return ruta
    except Exception: return None

app = FastAPI()
@app.get("/api/version")
async def api_version(): return {"version": VERSION}

FAQ=[(["credito","titular","titul"],"¿Cuántos créditos necesito para titularme en Traducción?"),(["costo","cuesta","precio","inscri"],"¿Cuánto cuesta inscribirme a las clases de inglés?"),(["horario","cec"],"¿Cuáles son los horarios del CEC?"),(["admision","requisito"],"¿Cuáles son los requisitos de admisión?"),(["carrera","tsu","tecnico","técnico"],"¿Qué carreras y programas técnicos ofrece?")]
def normalizar_faq(t):
    low=(t or "").lower()
    for k,c in FAQ:
        if any(x in low for x in k) and len(low)<90: return c
    return t or ""
def limpiar_tags(t): return re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+","",t or "").strip()
def github_subir(ruta,cont):
    if not GH_TOKEN or not GH_REPO: return "(sin respaldo)"
    try:
        url=f"https://api.github.com/repos/{GH_REPO}/contents/{ruta}"; h={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"}
        r=requests.get(url,headers=h,timeout=15); data={"message":f"bot: {ruta}","content":base64.b64encode(cont).decode()}
        if r.status_code==200 and r.json().get("sha"): data["sha"]=r.json()["sha"]
        q=requests.put(url,json=data,headers=h,timeout=25)
        return "☁️ Respaldo listo." if q.status_code in (200,201) else "⚠️ No respaldado."
    except Exception: return "⚠️ No respaldado."
def github_borrar(ruta):
    if not GH_TOKEN or not GH_REPO: return
    try:
        url=f"https://api.github.com/repos/{GH_REPO}/contents/{ruta}"; h={"Authorization":f"token {GH_TOKEN}","Accept":"application/vnd.github+json"}
        r=requests.get(url,headers=h,timeout=15)
        if r.status_code==200 and r.json().get("sha"): requests.delete(url,json={"message":f"bot: borra {ruta}","sha":r.json()["sha"]},headers=h,timeout=25)
    except Exception: pass
def log_uso(t,l,v):
    try: open(USO,"a",encoding="utf-8").write(json.dumps({"ts":datetime.now().isoformat(),"texto":t,"lang":l,"via":v},ensure_ascii=False)+"\n")
    except Exception: pass
def leer_uso():
    try: return [json.loads(l) for l in open(USO,encoding="utf-8") if l.strip()]
    except Exception: return []
def registrar_meta(arch,cat,resp):
    meta=_jload(DOCS_META,[]); meta.append({"archivo":arch,"categoria":cat,"responsable":resp or "sin asignar","fecha":datetime.now().isoformat()}); _jdump(DOCS_META,meta[-200:])
def guardar_aviso(texto,categoria="Avisos",responsable=""):
    try: os.remove(CACHE)
    except Exception: pass
    nuevo=datetime.now().strftime("%Y%m%d_%H%M")+"_"+categoria+".txt"
    cab=f"=== {categoria} | Subido: {datetime.now().strftime('%d/%m/%Y')} | Responsable: {responsable or 'sin asignar'} ===\n"
    cont=cab+texto
    open(os.path.join(CARPETA,nuevo),"w",encoding="utf-8").write(cont)
    registrar_meta(nuevo,categoria,responsable)
    return nuevo,github_subir(f"datos_bot/{nuevo}",cont.encode())
def extraer_texto(ruta,nombre):
    if nombre.lower().endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(ruta).pages)
    return open(ruta,encoding="utf-8",errors="ignore").read()

def router(msg,hist,state,lang_pref,rol="externo"):
    state=state or {"pending":False,"active":False}; texto=(msg or "").strip()
    if state.get("pending"):
        state["pending"]=False
        if texto==CLAVE_ADMIN: state["active"]=True; return "✅ Acceso concedido. SALIR para cerrar.",None,state
        return "❌ Clave incorrecta.",None,state
    if state.get("active"):
        if texto.upper()=="SALIR": state["active"]=False; return " Cerrado.",None,state
        n,r=guardar_aviso(texto); return f"✅ Publicado. {r}",None,state
    if "administraci" in texto.lower(): state["pending"]=True; return "🔐 Escribe la clave.",None,state
    try: resp,lang=responder(normalizar_faq(texto),hist or [],lang_pref,rol)
    except Exception: resp,lang=responder(normalizar_faq(texto),[],lang_pref,rol)
    return limpiar_tags(resp),lang,state

async def producir_audio(resp,lang):
    try:
        ruta=await generar_voz(resp,lang or "es")
        if ruta:
            n=str(uuid.uuid4())+".mp3"; d=os.path.join(AUDIOS,n)
            open(d,"wb").write(open(ruta,"rb").read()); return "/audio/"+n
    except Exception: pass
    return None

@app.post("/api/register")
async def api_register(req:Request):
    d=await req.json(); u=(d.get("usuario") or "").strip().lower(); c=d.get("clave") or ""
    if len(u)<3 or len(c)<4: return {"ok":False,"error":"Usuario ≥3 y clave ≥4."}
    users=_jload(USERS,{})
    if u in users: return {"ok":False,"error":"Ya existe."}
    s=secrets.token_hex(8); users[u]={"salt":s,"hash":_hash(c,s),"rol":"interno" if u.endswith("@uabc.edu.mx") else "externo"}
    _jdump(USERS,users); return {"ok":True,"usuario":u,"rol":users[u]["rol"]}
@app.post("/api/login")
async def api_login(req:Request):
    d=await req.json(); u=(d.get("usuario") or "").strip().lower(); c=d.get("clave") or ""
    rec=_jload(USERS,{}).get(u)
    if not rec or rec["hash"]!=_hash(c,rec["salt"]): return {"ok":False,"error":"Credenciales incorrectas."}
    return {"ok":True,"usuario":u,"rol":rec.get("rol","externo")}
@app.post("/api/chat")
async def api_chat(req:Request):
    d=await req.json(); st=d.get("state") or {}; rol=d.get("rol","externo")
    if not (st.get("active") or st.get("pending")): log_uso(d.get("msg",""),d.get("lang","auto"),"texto")
    try: r,l,s=router(d.get("msg"),d.get("hist"),st,d.get("lang","auto"),rol); a=await producir_audio(r,l)
    except Exception as e: r=f"⚠️ Error: {type(e).__name__}"; a=None; s=st; l="es"
    return {"reply":r,"audio":a,"state":s,"lang":l}
@app.post("/api/voice")
async def api_voice(audio:UploadFile=File(...),hist:str=Form("[]"),state:str=Form("{}"),lang:str=Form("auto"),rol:str=Form("externo")):
    data=await audio.read(); texto,_=transcribir(data)
    if not texto: return {"texto":"","reply":"⚠️ No escuché bien.","audio":None,"state":state,"lang":"es"}
    st=json.loads(state)
    if not (st.get("active") or st.get("pending")): log_uso(texto,lang,"voz")
    r,l,s=router(texto,json.loads(hist),st,lang,rol); a=await producir_audio(r,l)
    return {"texto":texto,"reply":r,"audio":a,"state":s,"lang":l}
@app.post("/api/voice_note")
async def voice_note(audio:UploadFile=File(...),categoria:str=Form("Avisos"),responsable:str=Form("")):
    data=await audio.read(); texto,_=transcribir(data)
    if not texto: return {"estado":"⚠️ No escuché la nota."}
    n,r=guardar_aviso(texto,categoria,responsable); return {"estado":f"✅ Nota publicada: {n}. {r}"}
@app.post("/api/unlock")
async def api_unlock(req:Request): return {"ok":(await req.json()).get("clave")==CLAVE_ADMIN}
@app.post("/api/resp/add")
async def resp_add(req:Request):
    d=await req.json(); lst=_jload(RESPONSABLES,[])
    lst.append({"nombre":d.get("nombre",""),"correo":d.get("correo",""),"rol":d.get("rol",""),"clases":d.get("clases",""),"fecha":datetime.now().isoformat()})
    _jdump(RESPONSABLES,lst); github_subir("responsables.json",json.dumps(lst,ensure_ascii=False,indent=1).encode())
    return {"ok":True}
@app.get("/api/resp/list")
async def resp_list(): return _jload(RESPONSABLES,[])
@app.post("/api/cat/add")
async def cat_add(req:Request):
    d=await req.json(); lst=_jload(CATALOGO,[])
    kw=[x.strip().lower() for x in (d.get("kw","") or "").split(",") if x.strip()]
    lst.append({"tema":d.get("tema",""),"kw":kw,"nombre":d.get("nombre",""),"rol":d.get("rol",""),"correo":d.get("correo",""),"tel":d.get("tel",""),"oficina":d.get("oficina",""),"horario":d.get("horario","")})
    _jdump(CATALOGO,lst); github_subir("catalogo.json",json.dumps(lst,ensure_ascii=False,indent=1).encode())
    try: os.remove(CACHE)
    except Exception: pass
    return {"ok":True}
@app.get("/api/cat/list")
async def cat_list(): return cargar_catalogo()
@app.get("/api/docs_meta")
async def docs_meta(): return _jload(DOCS_META,[])
@app.post("/api/report")
async def report(req:Request):
    d=await req.json()
    if d.get("clave")!=CLAVE_ADMIN: return {"error":"❌ Clave incorrecta"}
    lines=leer_uso(); hoy=datetime.now().strftime("%Y-%m-%d")
    c=Counter(normalizar_faq(l["texto"]) for l in lines if l.get("texto")); idi=Counter(l.get("lang","auto") for l in lines)
    pend=[]
    for fn in sorted(os.listdir(FEEDBACK),reverse=True)[:15]:
        try:
            txt=open(os.path.join(FEEDBACK,fn),encoding="utf-8").read()
            a=re.search(r"Área: (.+?) \|",txt); pg=re.search(r"PREGUNTA: (.+)",txt)
            ar=a.group(1).strip() if a else "Otro"
            pend.append({"area":ar,"responsable":AREAS_RESP.get(ar,AREAS_RESP["Otro"]),"pregunta":pg.group(1).strip() if pg else ""})
        except Exception: pass
    return {"total":len(lines),"hoy":sum(1 for l in lines if l.get("ts","").startswith(hoy)),"top":c.most_common(10),"idiomas":dict(idi),"pendientes":pend,"subidas":_jload(DOCS_META,[])[-10:],"catalogo":len(cargar_catalogo())}
@app.get("/api/topfaq")
async def topfaq():
    now=time.time()
    try:
        c=json.load(open(TOPFAQ_CACHE,encoding="utf-8"))
        if now-c.get("ts",0)<TOPFAQ_HOURS*3600: return c["items"]
    except Exception: pass
    cnt=Counter(normalizar_faq(l["texto"]) for l in leer_uso() if l.get("texto"))
    items=[{"q":q,"n":n} for q,n in cnt.most_common(8)]
    try: json.dump({"ts":now,"items":items},open(TOPFAQ_CACHE,"w",encoding="utf-8"),ensure_ascii=False)
    except Exception: pass
    return items
@app.get("/api/tts")
async def api_tts(texto:str="",lang:str="es"):
    try:
        ruta=await generar_voz(texto,lang if lang in VOCES else "es")
        if ruta:
            n=str(uuid.uuid4())+".mp3"; d=os.path.join(AUDIOS,n); open(d,"wb").write(open(ruta,"rb").read()); return {"url":"/audio/"+n}
    except Exception: pass
    return {"url":""}
@app.post("/api/feedback")
async def api_feedback(req:Request):
    d=await req.json(); ts=datetime.now().strftime("%Y%m%d_%H%M%S"); area=d.get("area","Otro")
    cap=d.get("captura",""); capurl=""
    if cap:
        try:
            hb,db=cap.split(",",1) if "," in cap else ("",cap); img=base64.b64decode(db); name=ts+".png"
            open(os.path.join(CAPTURAS,name),"wb").write(img); github_subir(f"capturas/{name}",img); capurl="/captura/"+name
        except Exception as e: capurl=f"(error: {e})"
    cont=f"=== Feedback {ts} | Área: {area} | Reenviar a: {AREAS_RESP.get(area,AREAS_RESP['Otro'])} ===\nCAPTURA: {capurl or 'no disp.'}\nPREGUNTA: {d.get('pregunta','')}\nRESPUESTA: {d.get('respuesta','')}\nCOMENTARIO: {d.get('comentario','')}\n"
    open(os.path.join(FEEDBACK,ts+".txt"),"w",encoding="utf-8").write(cont); github_subir(f"feedback/{ts}.txt",cont.encode())
    return {"ok":True,"captura":capurl}
@app.get("/captura/{n}")
async def captura(n:str): return FileResponse(os.path.join(CAPTURAS,n),media_type="image/png")
@app.get("/api/feedback/list")
async def fb_list(clave:str=""):
    if clave!=CLAVE_ADMIN: return {"items":["❌ Clave incorrecta"]}
    out=[]
    for fn in sorted(os.listdir(FEEDBACK),reverse=True)[:10]:
        try: out.append(open(os.path.join(FEEDBACK,fn),encoding="utf-8").read())
        except Exception: pass
    return {"items":out or ["Sin feedbacks. 🎉"]}
@app.post("/api/upload")
async def api_upload(archivo:UploadFile=File(None),categoria:str=Form("Avisos"),vigencia:str=Form(""),reemplazar:str=Form("0"),texto_manual:str=Form(""),responsable:str=Form("")):
    texto=texto_manual.strip()
    if archivo is not None: nom=archivo.filename or "doc.txt"; ext=os.path.splitext(nom)[1].lower(); data=await archivo.read()
    else: nom="nota_manual.txt"; ext=".txt"; data=b""
    if ext in EXT_IMG:
        mime="image/png" if ext==".png" else "image/jpeg"
        if not texto: texto,err=extraer_imagen(data,mime)
        else: err=""
        if not texto: return {"estado":f"⚠️ Visión no disp. ({err}). Pega el texto en 📝."}
        iname=str(uuid.uuid4())+ext; open(os.path.join(IMGS,iname),"wb").write(data); texto+=f"\n️ Póster: /img/{iname}"
    elif data:
        tmp=os.path.join(BASE,"tmp_"+nom); open(tmp,"wb").write(data); texto=extraer_texto(tmp,nom) or texto; os.remove(tmp)
    if not texto: return {"estado":"⚠️ Elige archivo o pega texto en 📝."}
    if reemplazar=="1":
        for fn in list(os.listdir(CARPETA)):
            if fn.endswith(f"_{categoria}.txt"): os.remove(os.path.join(CARPETA,fn)); github_borrar(f"datos_bot/{fn}")
    nuevo,resp=guardar_aviso(texto,categoria,responsable)
    return {"estado":f"✅ Guardado {nuevo} (Responsable: {responsable or 'sin asignar'}). {resp}"}
@app.post("/api/delete")
async def api_delete(req:Request):
    d=await req.json()
    if d.get("clave")!=CLAVE_ADMIN: return {"estado":"❌ Clave incorrecta"}
    n=(d.get("nombre") or "").strip(); r=os.path.join(CARPETA,n)
    if os.path.exists(r): os.remove(r); github_borrar(f"datos_bot/{n}"); return {"estado":f"️ {n} eliminado."}
    return {"estado":"No encontrado."}
@app.get("/api/docs")
async def api_docs(): return {"docs":[f for f in sorted(os.listdir(CARPETA)) if f.endswith(".txt")]}
@app.get("/api/cache/clear")
async def cache_clear(clave:str=""):
    if clave!=CLAVE_ADMIN: return {"ok":False}
    try: os.remove(CACHE)
    except Exception: pass
    return {"ok":True}
@app.get("/api/debug")
async def api_debug():
    out={"version":VERSION,"gemini":bool(cliente_gemini),"groq":bool(GROQ_KEY),"openrouter":bool(OR_KEY)}
    try: t,l=responder("Di solo: listo",[]); out["respuesta"]=t[:100]
    except Exception as e: out["error"]=f"{type(e).__name__}: {e}"
    return out
@app.get("/wa/webhook")
async def wa_verify(request:Request):
    q=request.query_params
    if q.get("hub.mode")=="subscribe" and q.get("hub.verify_token")==WA_VERIFY:
        from fastapi.responses import Response as _R
        return _R(content=q.get("hub.challenge",""),media_type="text/plain")
    return JSONResponse({"error":"invalid"},status_code=403)
@app.post("/wa/webhook")
async def wa_incoming(req:Request):
    try:
        d=await req.json(); v=d["entry"][0]["changes"][0]["value"]
        if "messages" in v:
            m=v["messages"][0]; texto=(m.get("text") or {}).get("body","")
            if texto: r,l=responder(texto,[],"auto","externo"); await wa_send(m["from"],r)
    except Exception: pass
    return {"ok":True}
async def wa_send(to,texto):
    if not WA_TOKEN or not WA_PHONE_ID: return
    try: requests.post(f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages",headers={"Authorization":f"Bearer {WA_TOKEN}","Content-Type":"application/json"},json={"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":texto}},timeout=20)
    except Exception: pass
@app.post("/api/conv/save")
async def conv_save(req:Request):
    d=await req.json(); cid=re.sub(r"[^a-zA-Z0-9_-]","",d.get("id",""))[:40] or "c"
    json.dump({"id":cid,"user":d.get("user",""),"titulo":d.get("titulo",""),"fecha":datetime.now().isoformat(),"msgs":d.get("msgs",[])},open(os.path.join(CONVS,cid+".json"),"w",encoding="utf-8"),ensure_ascii=False)
    return {"ok":True}
@app.get("/api/conv/list")
async def conv_list(user:str=""):
    out=[]
    for fn in os.listdir(CONVS):
        if fn.endswith(".json"):
            try:
                d=json.load(open(os.path.join(CONVS,fn),encoding="utf-8"))
                if user and d.get("user")!=user: continue
                out.append({"id":d["id"],"titulo":d.get("titulo",""),"fecha":d.get("fecha","")})
            except Exception: pass
    out.sort(key=lambda x:x["fecha"],reverse=True); return out[:30]
@app.get("/api/conv/get")
async def conv_get(id:str=""):
    cid=re.sub(r"[^a-zA-Z0-9_-]","",id)[:40]; p=os.path.join(CONVS,cid+".json")
    return json.load(open(p,encoding="utf-8")) if os.path.exists(p) else {}
@app.get("/audio/{n}")
async def audio(n:str): return FileResponse(os.path.join(AUDIOS,n),media_type="audio/mpeg")
@app.get("/img/{n}")
async def img(n:str): return FileResponse(os.path.join(IMGS,n),media_type="image/png" if n.endswith(".png") else "image/jpeg")
@app.get("/logo.png")
async def logo(): return FileResponse(LOGO) if os.path.exists(LOGO) else JSONResponse({})

PAGINA = """
<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>UABCBot Idiomas — Facultad de Idiomas de la UABC en Mexicali</title>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}body{background:#eef1f4}
#toast{display:none;position:fixed;top:12px;left:50%;transform:translateX(-50%);color:#fff;padding:13px 22px;border-radius:14px;font-size:14.5px;z-index:99;box-shadow:0 4px 16px rgba(0,0,0,.35);max-width:92%;text-align:center}
.wrap{max-width:100%;margin:0 auto;height:100vh;display:flex;flex-direction:row}
#side{width:260px;background:#004d38;color:#fff;padding:14px 10px;display:flex;flex-direction:column;gap:8px;overflow-y:auto}
#side b{font-size:14px}#side button{background:rgba(255,255,255,.12);color:#fff;border:none;border-radius:10px;padding:9px 10px;text-align:left;cursor:pointer;font-size:12.5px}
main{flex:1;display:flex;flex-direction:column;height:100vh}
header{background:linear-gradient(135deg,#00684a,#00855f);color:#fff;padding:12px 16px;display:flex;align-items:center;gap:10px;border-radius:0 0 18px 18px;flex-wrap:wrap}
header img{width:54px;height:54px;background:#fff;border-radius:12px;padding:3px}header h1{font-size:17px}header p{font-size:12px;opacity:.85}
.langs{display:flex;gap:5px;margin-left:10px}.langs button{font-size:11px;padding:4px 8px;border-radius:999px;border:1px solid rgba(255,255,255,.5);background:transparent;color:#fff;cursor:pointer}
.langs button.on{background:#f7941d;border-color:#f7941d;font-weight:700}
.hbtn{background:rgba(255,255,255,.15);border:none;border-radius:999px;width:36px;height:36px;cursor:pointer;font-size:16px}#user{background:#8fe3b0}#nuevo{margin-left:auto}
#chat{flex:1;overflow-y:auto;padding:16px 12px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:82%;display:flex;flex-direction:column;gap:4px}.msg.user{align-self:flex-end;align-items:flex-end}.msg.bot{align-self:flex-start;align-items:flex-start}
.bub{padding:10px 14px;border-radius:16px;font-size:calc(14.5px * var(--fs,1));line-height:1.45;box-shadow:0 1px 2px rgba(0,0,0,.12);white-space:pre-wrap}
.user .bub{background:#d9f6c8;border-bottom-right-radius:4px}.bot .bub{background:#fff;border-bottom-left-radius:4px}
.msg audio{width:260px;max-width:100%}.think .bub{background:#fff;color:#666;font-style:italic}
.dots::after{content:'';animation:pts 1.2s steps(4) infinite}@keyframes pts{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
.opts{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.opts button{font-size:calc(12.5px * var(--fs,1));padding:7px 11px;border-radius:999px;border:1px solid #00855f;background:#f2fbf6;color:#00684a;cursor:pointer}
.nota{display:block;margin-top:9px;font-size:calc(12px * var(--fs,1));color:#888}
.bar{display:flex;gap:8px;padding:10px 12px 14px;align-items:center}
#mic{width:46px;height:46px;border-radius:50%;border:none;background:#00684a;color:#fff;font-size:19px;cursor:pointer;flex-shrink:0}#mic.rec{background:#d32f2f;animation:pulso 1s infinite}@keyframes pulso{50%{transform:scale(1.12)}}
#inp{flex:1;border:1px solid #cfd8dc;border-radius:999px;padding:12px 18px;font-size:calc(15px * var(--fs,1));outline:none}
#send{width:46px;height:46px;border-radius:50%;border:none;background:#f7941d;color:#fff;font-size:18px;cursor:pointer;flex-shrink:0}
#fb{width:46px;height:46px;border-radius:50%;border:none;background:#d32f2f;color:#fff;font-size:17px;cursor:pointer;flex-shrink:0}
#gear{position:fixed;right:10px;top:74px;background:rgba(0,0,0,.25);border:none;color:#fff;border-radius:50%;width:30px;height:30px;cursor:pointer;z-index:5}
#convs{display:none}
.drawer{display:none;background:#fff;margin:0 12px 8px;border-radius:14px;padding:12px;box-shadow:0 2px 10px rgba(0,0,0,.15);font-size:13px;max-height:60vh;overflow-y:auto}
.drawer input,.drawer select,.drawer textarea{margin:4px 0;padding:8px;border-radius:8px;border:1px solid #cfd8dc;width:100%}
.drawer button{margin-top:6px;padding:8px 12px;border-radius:10px;border:none;background:#00684a;color:#fff;cursor:pointer}
.drawer .item{display:block;width:100%;background:#f2f4f7;color:#222;margin:4px 0;text-align:left}
.xbtn{background:#d32f2f!important;float:right}
#drop{border:2px dashed #00855f;border-radius:12px;padding:14px;text-align:center;color:#00684a;background:#f2fbf6;margin:6px 0;cursor:pointer}
#dlist{white-space:pre-wrap;background:#f7f9fa;border-radius:8px;padding:8px;margin-top:6px;font-size:12px}
.etiq{display:block;margin:8px 0 2px;font-weight:700;color:#00684a}.ayuda{font-size:11.5px;color:#667;margin-bottom:4px}
.fb-captura{margin-top:8px;border:1px solid #cfd8dc;border-radius:8px;padding:8px;text-align:center;background:#f7f9fa;font-size:11.5px;color:#556}
@media(max-width:900px){#side{display:none}#convs{display:block}}
@media(min-width:900px){.bub{font-size:calc(16.5px * var(--fs,1))}header h1{font-size:21px}header p{font-size:13px}#inp{font-size:calc(17px * var(--fs,1));padding:14px 22px}.msg{max-width:70%}}
</style></head><body>
<div id="toast"></div>
<div class="wrap">
<aside id="side"><b id="sidet">🗂️ Conversaciones</b><button id="sidenew">➕ Nueva conversación</button><div id="lista"></div></aside>
<main>
<header>
<img src="/logo.png" alt="logo"><div><h1>UABCBot Idiomas</h1><p id="hsub">Facultad de Idiomas de la UABC en Mexicali</p></div>
<div class="langs"><button id="Lauto" class="on">AUTO</button><button id="Les">ES</button><button id="Len">EN</button><button id="Lfr">FR</button></div>
<div class="langs" style="margin-left:4px"><button id="fmenos">A−</button><button id="fmas">A+</button><button id="full">⛶</button></div>
<button id="convs" class="hbtn">🗂️</button><button id="user" class="hbtn">👤</button><button id="logout" class="hbtn">🚪</button><button id="nuevo" class="hbtn">🧹</button>
</header>
<button id="gear">️</button>
<div id="cdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖</button><b id="sidet2">️ Conversaciones</b><div id="lista2"></div></div>
<div id="udrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖</button><b id="utitle">👤 Tu cuenta</b><div id="who"></div>
<input id="uusr" placeholder="Correo (@uabc.edu.mx si eres UABC)"><input id="ukey" type="password" placeholder="Clave">
<button id="ureg">✨ Registrarme</button><button id="ulin">🔑 Entrar</button><button id="uguest">👋 Invitado</button><button id="uout">🚪 Cerrar sesión</button></div>
<div id="chat"></div>
<div id="fbdrawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖</button><b id="fbtitle">🚩 Reportar respuesta</b>
<span class="etiq" id="fbarea_l">Área responsable</span><select id="fbarea"><option>Admisión</option><option>CEC</option><option>Escolar/Escolaridad</option><option>Egresados/Bolsa de trabajo</option><option>Eventos</option><option>Otro</option></select>
<span class="etiq" id="fbcom_l">Cuéntanos qué faltó</span><textarea id="fbcom" rows="3"></textarea><div id="fbprev" class="fb-captura">📸 Captura automática adjunta.</div>
<button id="fbsend">📨 Enviar al responsable</button></div>
<div id="drawer" class="drawer"><button class="xbtn" onclick="this.parentNode.style.display='none'">✖</button><b>🛠️ Panel de personal</b>
<input id="clave" type="password" placeholder="Clave (Enter)"><button id="unlock"> Entrar</button><button id="salirp">🚪 Salir</button>
<div id="zona" style="display:none">
<span class="etiq">📇 Catálogo: agregar responsable por tema</span>
<input id="ctema" placeholder="Tema (ej. Doctorados)"><input id="ckw" placeholder="Palabras clave, separadas por coma (doctorado, posgrado)"><input id="cnom" placeholder="Nombre del responsable"><input id="crol" placeholder="Rol"><input id="ccor" placeholder="Correo"><input id="ctel" placeholder="Teléfono"><input id="cof" placeholder="Oficina"><input id="chor" placeholder="Horario de atención">
<button id="cadd">➕ Agregar al catálogo</button>
<span class="etiq">👥 Registrar profesor</span>
<input id="rnom" placeholder="Nombre"><input id="rcor" placeholder="Correo @uabc.edu.mx"><input id="rrol" placeholder="Rol"><input id="rcla" placeholder="Clases que imparte">
<button id="radd">➕ Agregar al directorio</button>
<span class="etiq">1️⃣ Categoría</span><select id="fcat"><option>Avisos</option><option>Eventos</option><option>Suspensiones</option><option>Horarios</option><option>Exámenes</option><option>Convocatorias</option><option>TSU</option><option>PlanDeEstudios</option><option>CEC</option><option>Clases</option><option>Tareas</option><option>Internos</option></select>
<span class="etiq">✍️ Responsable</span><input id="fresp" list="resplist" placeholder="Nombre"><datalist id="resplist"></datalist>
<span class="etiq">2️⃣ Vigente hasta</span><input id="fvig" type="date">
<span class="etiq">3️⃣ Archivo</span><div id="drop">📥 Arrastra o toca</div><input id="ffile" type="file" style="display:none">
<span class="etiq">📝 Texto (plan B)</span><textarea id="ftexto" rows="4"></textarea>
<button id="fsubir">📤 Subir y publicar</button><button id="nota">🎤 Nota de voz</button><button id="ldocs">🔄 Documentos</button><button id="lfb">📨 Feedbacks</button><button id="rep">📊 Reporte</button>
<div id="dlist"></div><span class="etiq">🗑️ Borrar</span><input id="fdel" placeholder="Nombre (Enter)"><button id="bdel">🗑️</button><div id="fest"></div>
</div></div>
<div class="bar"><button id="mic">🎤</button><input id="inp" placeholder="Escribe o dime tu pregunta…"><button id="send">➤</button><button id="fb"></button></div>
</main></div>
<script>
let hist=[],state={pending:false,active:false},langPref="auto",rec=null,rec2=null,chunks=[],currentId=uid(),droppedFile=null,thinkTimer=null,thinkSec=0,toastTimer=null,lastP="",lastR="",capPend="",fontScale=1;
let currentUser=localStorage.getItem('uabc_user')||"",currentRol=localStorage.getItem('uabc_rol')||"externo";
const chat=document.getElementById('chat'),inp=document.getElementById('inp');
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const B={es:'👋 ¡Hola! Soy <b>UABCBot Idiomas</b> de la Facultad de Idiomas UABC Mexicali. Te atiendo en español, inglés o francés: <b>te leo o te escucho</b>.',en:'👋 Hi! I am <b>UABCBot Idiomas</b>. I serve you in Spanish, English or French: <b>I read you or listen to you</b>.',fr:'👋 Bonjour ! Je suis <b>UABCBot Idiomas</b>. Je t\'aide en espagnol, anglais ou français : <b>je te lis ou je t\'écoute</b>.'};
const TB={es:'¡Hola! Soy UABCBot Idiomas. Te leo o te escucho en español, inglés o francés.',en:'Hi! I am UABCBot Idiomas. I read you or listen to you.',fr:'Bonjour ! Je suis UABCBot Idiomas. Je te lis ou je t\'écoute.'};
const N={es:'Docentes: di "administración". Comunidad UABC: regístrate con @uabc.edu.mx. Si algo no te resuelve, toca .',en:'Staff: type "administración". UABC: register with @uabc.edu.mx. If not solved, tap 🚩.',fr:'Personnel : « administración ». UABC : inscris-toi avec @uabc.edu.mx. Sinon, touche .'};
const G={es:'👋 Invitado: sin memoria. Regístrate con 👤.',en:'👋 Guest: no memory. Register with 👤.',fr:'👋 Invité : pas de mémoire.'};
const UI={es:{sub:"Facultad de Idiomas de la UABC en Mexicali",side:"🗂️ Conversaciones",new:"➕ Nueva conversación",ph:"Escribe o dime tu pregunta…",ut:" Tu cuenta",reg:"✨ Registrarme",log:"🔑 Entrar",gue:"👋 Invitado",out:"🚪 Cerrar sesión",co:"Correo (@uabc.edu.mx si eres UABC)",cl:"Clave"},en:{sub:"Faculty of Languages of UABC in Mexicali",side:"🗂️ Conversations",new:"➕ New conversation",ph:"Type or say your question…",ut:"👤 Your account",reg:"✨ Register",log:"🔑 Sign in",gue:"👋 Guest",out:"🚪 Sign out",co:"Email (@uabc.edu.mx if UABC)",cl:"Password"},fr:{sub:"Faculté de Langues de l'UABC à Mexicali",side:"️ Conversations",new:"➕ Nouvelle conversation",ph:"Écris ou dis ta question…",ut:"👤 Ton compte",reg:"✨ M'inscrire",log:"🔑 Entrer",gue:"👋 Invité",out:"🚪 Sortir",co:"Courriel (@uabc.edu.mx)",cl:"Mot de passe"}};
const WHO={es:{i:' · ✅ comunidad UABC',e:' · público',g:'👋 Invitado: sin memoria.'},en:{i:' · ✅ UABC community',e:' · public',g:'👋 Guest: no memory.'},fr:{i:' · ✅ communauté UABC',e:' · public',g:'👋 Invité.'}};
const OB={"¿Cuántos créditos necesito para titularme en Traducción?":{es:"💳 Créditos",en:"💳 Credits",fr:"💳 Crédits"},"¿Cuánto cuesta inscribirme a las clases de inglés?":{es:"💰 Costo inglés",en:"💰 English cost",fr:"💰 Coût"},"¿Cuáles son los requisitos de admisión a la Facultad de Idiomas?":{es:"🎓 Admisión",en:"🎓 Admission",fr:"🎓 Admission"},"¿Qué carreras y programas técnicos ofrece la Facultad de Idiomas?":{es:"🏛️ Carreras",en:"🏛️ Degrees",fr:"🏛️ Licences"}};
function uid(){return 'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,7)}
function langUI(){return (langPref in B)?langPref:'es'}
function applyFont(){document.documentElement.style.setProperty('--fs',fontScale)}
function applyLang(L){const u=UI[L]||UI.es;hsub.innerText=u.sub;sidet.innerText=u.side;sidet2.innerText=u.side;sidenew.innerText=u.new;inp.placeholder=u.ph;utitle.innerText=u.ut;ureg.innerText=u.reg;ulin.innerText=u.log;uguest.innerText=u.gue;uout.innerText=u.out;uusr.placeholder=u.co;ukey.placeholder=u.cl}
function avisar(m,t){const e=document.getElementById('toast');e.innerText=m;e.style.background=t==='error'?'#d32f2f':t==='ok'?'#00684a':'#f7941d';e.style.display='block';if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(()=>e.style.display='none',7000)}
function bubble(r,t,a){const d=document.createElement('div');d.className='msg '+r;let h='<div class="bub">'+esc(t)+'</div>';if(a)h+='<audio controls src="'+a+'"></audio>';d.innerHTML=h;chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d}
async function welcome(){const L=langUI();applyLang(L);let o=Object.keys(OB).map(q=>({q,t:OB[q][L]}));
try{const d=await(await fetch('/api/topfaq')).json();o=o.concat((d||[]).filter(x=>!OB[x.q]).map(x=>({q:x.q,t:"🔥 "+(x.q.length>40?x.q.slice(0,40)+"…":x.q)})).slice(0,4))}catch(e){}
const d=document.createElement('div');d.className='msg bot';d.innerHTML='<div class="bub">'+B[L]+'<div class="opts">'+o.map(x=>'<button data-q="'+esc(x.q)+'">'+esc(x.t)+'</button>').join('')+'</div><span class="nota">'+N[L]+'</span></div>';chat.appendChild(d);
d.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>send(b.dataset.q));
try{const a=await(await fetch('/api/tts?lang='+L+'&texto='+encodeURIComponent(TB[L]))).json();if(a.url){const au=document.createElement('audio');au.controls=true;au.src=a.url;d.querySelector('.bub').appendChild(au)}}catch(e){}
chat.scrollTop=chat.scrollHeight}
function thinking(){removeThink();const d=document.createElement('div');d.className='msg bot think';d.id='think';d.innerHTML='<div class="bub">🤔 <span id="tsec">0</span> s</div>';chat.appendChild(d);thinkSec=0;thinkTimer=setInterval(()=>{thinkSec++;const e=document.getElementById('tsec');if(e)e.textContent=thinkSec},1000)}
function removeThink(){if(thinkTimer){clearInterval(thinkTimer);thinkTimer=null}const t=document.getElementById('think');if(t)t.remove()}
function refreshWho(){const L=langUI(),w=WHO[L];who.innerText=currentUser?'✅ '+currentUser+(currentRol==='interno'?w.i:w.e):w.g}
function doLogout(){currentUser="";currentRol="externo";localStorage.removeItem('uabc_user');localStorage.removeItem('uabc_rol');refreshWho();loadList();udrawer.style.display='none';avisar('')}
function saveConv(){if(!currentUser)return;const t=((hist.find(m=>m.role==='user')||{}).content||'Nueva').slice(0,40);fetch('/api/conv/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:currentId,user:currentUser,titulo:t,msgs:hist})}).then(loadList)}
async function loadList(){if(!currentUser){const m='<small>'+(G[langUI()]||G.es)+'</small>';lista.innerHTML=m;lista2.innerHTML=m;return}
const d=await(await fetch('/api/conv/list?user='+encodeURIComponent(currentUser))).json();const h=d.map(c=>'<button class="item" data-id="'+c.id+'">'+esc(c.titulo)+'</button>').join('');lista.innerHTML=h||'<small>—</small>';lista2.innerHTML=h||'<small>—</small>';document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>openConv(b.dataset.id))}
async function openConv(id){const d=await(await fetch('/api/conv/get?id='+id)).json();if(!d.msgs)return;currentId=id;hist=d.msgs;state={pending:false,active:false};chat.innerHTML='';hist.forEach(m=>bubble(m.role,m.content,m.audio));cdrawer.style.display='none'}
function nueva(){currentId=uid();hist=[];state={pending:false,active:false};chat.innerHTML='';welcome();loadList();cdrawer.style.display='none'}
async function loadResp(){const d=await(await fetch('/api/resp/list')).json();resplist.innerHTML=(d||[]).map(r=>'<option value="'+esc(r.nombre)+'"></option>').join('')}
async function send(m){if(!m.trim())return;const ek=state.pending;const el=bubble('user',m);hist.push({role:'user',content:ek?'••••••':m});if(ek)setTimeout(()=>{el.querySelector('.bub').textContent='🔑 ••••••'},30000);inp.value='';lastP=m;thinking();
const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({msg:m,hist:hist.slice(-7),state,lang:langPref,rol:currentRol})});const d=await r.json();removeThink();state=d.state;lastR=d.reply;if(langPref==='auto'&&d.lang)applyLang(d.lang);hist.push({role:'assistant',content:d.reply,audio:d.audio});bubble('bot',d.reply,d.audio);saveConv()}
send.onclick=()=>send(inp.value);inp.onkeydown=e=>{if(e.key==='Enter')send(inp.value)};
nuevo.onclick=nueva;sidenew.onclick=nueva;
convs.onclick=()=>{cdrawer.style.display=cdrawer.style.display==='block'?'none':'block';loadList()};
user.onclick=()=>{udrawer.style.display=udrawer.style.display==='block'?'none':'block';refreshWho()};
logout.onclick=doLogout;
fmas.onclick=()=>{fontScale=Math.min(1.6,fontScale+.1);applyFont();avisar(' '+Math.round(fontScale*100)+'%')};
fmenos.onclick=()=>{fontScale=Math.max(.8,fontScale-.1);applyFont();avisar('🔍 '+Math.round(fontScale*100)+'%')};
full.onclick=()=>{if(!document.fullscreenElement)document.documentElement.requestFullscreen();else document.exitFullscreen()};
fb.onclick=async()=>{if(!lastR){avisar('⚠️ Nada que reportar','error');return}try{const c=await html2canvas(chat,{backgroundColor:'#eef1f4',scale:1,logging:false});capPend=c.toDataURL('image/png')}catch(e){capPend=''}fbdrawer.style.display=fbdrawer.style.display==='block'?'none':'block'};
fbsend.onclick=async()=>{avisar('⏳ Enviando…');await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pregunta:lastP,respuesta:lastR,comentario:fbcom.value,area:fbarea.value,captura:capPend})});fbcom.value='';fbdrawer.style.display='none';avisar('📨 Enviado al responsable.','ok')};
ureg.onclick=async()=>{const d=await(await fetch('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:uusr.value,clave:ukey.value})})).json();if(!d.ok)return avisar(d.error,'error');currentUser=d.usuario;currentRol=d.rol;localStorage.setItem('uabc_user',currentUser);localStorage.setItem('uabc_rol',currentRol);refreshWho();loadList();udrawer.style.display='none';avisar('✅ '+currentUser,'ok')};
ulin.onclick=async()=>{const d=await(await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:uusr.value,clave:ukey.value})})).json();if(!d.ok)return avisar(d.error,'error');currentUser=d.usuario;currentRol=d.rol;localStorage.setItem('uabc_user',currentUser);localStorage.setItem('uabc_rol',currentRol);refreshWho();loadList();udrawer.style.display='none';avisar('✅ '+currentUser,'ok')};
uguest.onclick=doLogout;uout.onclick=doLogout;
[['Lauto','auto'],['Les','es'],['Len','en'],['Lfr','fr']].forEach(([id,v])=>{document.getElementById(id).onclick=e=>{langPref=v;document.querySelectorAll('.langs button').forEach(x=>x.classList.remove('on'));e.target.classList.add('on');applyLang(langUI());refreshWho();loadList();if(!hist.length){chat.innerHTML='';welcome()}else avisar('🌐 '+v.toUpperCase())}});
drop.onclick=()=>ffile.click();drop.ondragover=e=>e.preventDefault();drop.ondrop=e=>{e.preventDefault();if(e.dataTransfer.files[0])marcar(e.dataTransfer.files[0])};
ffile.onchange=e=>{if(e.target.files[0])marcar(e.target.files[0])};
function marcar(f){droppedFile=f;drop.innerHTML='📎 '+esc(f.name);avisar('📎 '+f.name)}
cadd.onclick=async()=>{if(!ctema.value||!cnom.value)return avisar('⚠️ Tema y nombre obligatorios','error');await fetch('/api/cat/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tema:ctema.value,kw:ckw.value,nombre:cnom.value,rol:crol.value,correo:ccor.value,tel:ctel.value,oficina:cof.value,horario:chor.value})});ctema.value=ckw.value=cnom.value=crol.value=ccor.value=ctel.value=cof.value=chor.value='';avisar('📇 Responsable agregado al catálogo','ok')};
radd.onclick=async()=>{if(!rnom.value)return avisar('⚠️ Falta nombre','error');await fetch('/api/resp/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre:rnom.value,correo:rcor.value,rol:rrol.value,clases:rcla.value})});rnom.value=rcor.value=rrol.value=rcla.value='';loadResp();avisar('👥 Agregado al directorio','ok')};
mic.onclick=async()=>{if(rec&&rec.state==='recording'){rec.stop();return}const s=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];rec=new MediaRecorder(s);rec.ondataavailable=e=>chunks.push(e.data);rec.onstop=async()=>{s.getTracks().forEach(t=>t.stop());mic.classList.remove('rec');thinking();const fd=new FormData();fd.append('audio',new Blob(chunks,{type:'audio/webm'}),'voz.webm');fd.append('hist',JSON.stringify(hist.slice(-7)));fd.append('state',JSON.stringify(state));fd.append('lang',langPref);fd.append('rol',currentRol);const d=await(await fetch('/api/voice',{method:'POST',body:fd})).json();removeThink();state=d.state;if(langPref==='auto'&&d.lang)applyLang(d.lang);if(d.texto){bubble('user','🎤 '+d.texto);hist.push({role:'user',content:d.texto});lastP=d.texto}if(d.reply){bubble('bot',d.reply,d.audio);hist.push({role:'assistant',content:d.reply,audio:d.audio});lastR=d.reply}saveConv()};rec.start();mic.classList.add('rec');avisar('🎤 Grabando…')};
gear.onclick=()=>{drawer.style.display=drawer.style.display==='block'?'none':'block'};
salirp.onclick=()=>{state={pending:false,active:false};drawer.style.display='none';zona.style.display='none'};
clave.onkeydown=e=>{if(e.key==='Enter')unlock.click()};fdel.onkeydown=e=>{if(e.key==='Enter')bdel.click()};
unlock.onclick=async()=>{const r=await fetch('/api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clave:clave.value})});const d=await r.json();zona.style.display=d.ok?'block':'none';if(d.ok){loadDocs();loadResp();avisar('✅ Panel abierto','ok')}else avisar('❌ Clave','error')};
fsubir.onclick=async()=>{const f=ffile.files[0]||droppedFile;if(!f&&!ftexto.value.trim())return avisar('️ Elige archivo o texto','error');avisar('⏳ Publicando…');const fd=new FormData();if(f)fd.append('archivo',f);fd.append('categoria',fcat.value);fd.append('vigencia',fvig.value);fd.append('reemplazar','0');fd.append('texto_manual',ftexto.value);fd.append('responsable',fresp.value||currentUser);const d=await(await fetch('/api/upload',{method:'POST',body:fd})).json();fest.innerText=d.estado;avisar(d.estado,d.estado.startsWith('✅')?'ok':'error');loadDocs()};
ldocs.onclick=loadDocs;async function loadDocs(){const d=await(await fetch('/api/docs')).json();dlist.innerText=(d.docs||[]).join('\\n')||'—'}
lfb.onclick=async()=>{const d=await(await fetch('/api/feedback/list?clave='+encodeURIComponent(clave.value))).json();fest.innerText=(d.items||[]).join('\\n----------\\n');avisar(' Feedbacks','ok')};
bdel.onclick=async()=>{const d=await(await fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clave:clave.value,nombre:fdel.value})})).json();fest.innerText=d.estado;avisar(d.estado,'ok');loadDocs()};
nota.onclick=async()=>{if(rec2&&rec2.state==='recording'){rec2.stop();return}const s=await navigator.mediaDevices.getUserMedia({audio:true});let ch=[];rec2=new MediaRecorder(s);rec2.ondataavailable=e=>ch.push(e.data);rec2.onstop=async()=>{s.getTracks().forEach(t=>t.stop());avisar('⏳ Transcribiendo…');const fd=new FormData();fd.append('audio',new Blob(ch,{type:'audio/webm'}),'nota.webm');fd.append('categoria',fcat.value);fd.append('responsable',fresp.value||currentUser);const d=await(await fetch('/api/voice_note',{method:'POST',body:fd})).json();fest.innerText=d.estado;avisar(d.estado,d.estado.startsWith('✅')?'ok':'error');loadDocs()};rec2.start();avisar('🔴 Grabando…')};
rep.onclick=async()=>{const d=await(await fetch('/api/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clave:clave.value})})).json();if(d.error)return avisar(d.error,'error');
let t='📊 Total: '+d.total+' · Hoy: '+d.hoy+' · Catálogo: '+d.catalogo+'\\n\\n🔥 MÁS PREGUNTADAS:\\n'+d.top.map((x,i)=>(i+1)+'. '+x[0]+' ('+x[1]+')').join('\\n');
t+='\\n\\n🚩 PENDIENTES (pedir corrección):\\n'+((d.pendientes||[]).map(p=>'• ['+p.area+'] '+p.pregunta+' → '+p.responsable).join('\\n')||'• Sin pendientes 🎉');
t+='\\n\\n QUIÉN SUBIÓ QUÉ:\\n'+((d.subidas||[]).map(s=>'• '+s.responsable+' → '+s.categoria+' ('+s.archivo+')').join('\\n')||'• —');
fest.innerText=t;avisar('📊 Reporte listo','ok')};
applyFont();welcome();loadList();refreshWho();inp.focus();
</script></body></html>
"""

@app.get("/")
async def inicio(): return HTMLResponse(PAGINA)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
