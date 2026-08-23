import os, re, uuid, json, time, base64, hashlib, secrets, tempfile, requests
from datetime import datetime, date, timedelta
from collections import Counter
from google import genai as genai_lib
from google.genai import types as gtypes
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn

VERSION = "v19-2026-08-22"
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

AREAS_RESP = {"Admision":"admision.mxl@uabc.edu.mx","CEC":"recepcionmxl@uabc.edu.mx","Escolar":"escolares_idiomas_mxl@uabc.edu.mx","Egresados":"egresados__idiomas__mxl@uabc.edu.mx","Eventos":"idiomas.mxl@uabc.edu.mx","Otro":"idiomas.mxl@uabc.edu.mx"}

CAT_DEF = [
 {"tema":"Doctorado / Posgrado (DCL)","kw":["doctorado","doctorados","dcl","posgrado","doctor"],"nombre":"Dr. Maldonado","rol":"Responsable de Doctorados","correo":"","tel":"686-689-0825","oficina":"","horario":""},
 {"tema":"Titulacion","kw":["titulacion","titularme","titular"],"nombre":"Responsable de Titulacion","rol":"Titulacion","correo":"","tel":"686-689-0825","oficina":"","horario":""},
 {"tema":"CEC / Cursos de idiomas","kw":["cec","curso","cursos","ingles","frances"],"nombre":"Responsable CEC","rol":"Centro de Ensenanza de Lenguas","correo":"recepcionmxl@uabc.edu.mx","tel":"686 841-82-91 ext. 300","oficina":"","horario":""},
 {"tema":"Egresados / Bolsa de trabajo","kw":["egresado","egresados","bolsa","empleo"],"nombre":"Mtra. Dulce Rodriguez Diaz","rol":"Responsable de Egresados y Bolsa de Trabajo","correo":"egresados__idiomas__mxl@uabc.edu.mx","tel":"686-689-0825","oficina":"","horario":""},
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
    else: s += f" Si llamas al 686-689-0825 pide que te canalicen directamente con {e['nombre']}; asi no das vueltas."
    return s

try:
    if not os.path.exists(LOGO):
        r = requests.get(LOGO_URL, timeout=10)
        if r.status_code == 200 and r.content: open(LOGO, "wb").write(r.content)
except Exception: pass

VOCES = {"es":"es-MX-DaliaNeural","en":"en-US-AriaNeural","fr":"fr-FR-DeniseNeural"}
DIAS = {0:"lunes",1:"martes",2:"miercoles",3:"jueves",4:"viernes",5:"sabado",6:"domingo"}
MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
MESES_INV = {v:k for k,v in MESES.items()}
MESES_ALT = "(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
EXT_IMG = (".png",".jpg",".jpeg",".webp")
PROMPT_POSTER = "Este es un anuncio o poster institucional. Extrae TODA la informacion util (que evento, quien invita, fecha, hora, lugar, contacto, requisitos) y devuelvela como texto claro en espanol, sin comentarios."

def fecha_hoy_es():
    n = datetime.now(); return f"{DIAS[n.weekday()]} {n.day} de {MESES[n.month]} de {n.year}"
def detectar_idioma(t):
    t = (t or "").lower()
    fr = ["bonjour","merci","combien","pour","avec","vous","diplom","traduction","salut","credit","je ","etud","francais","voud","veux","quel","quelle","aime","les ","des ","anglais"]
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
 (["credito","titular","credit"], {"es":"Para titularte en la Licenciatura en Traduccion (LT) necesitas 349 creditos: 237 obligatorios, 102 optativos y 10 de practicas. Detalles: idiomas.mxl.uabc.mx o 686-689-0825.","en":"To graduate from Translation (LT) you need 349 credits: 237 mandatory, 102 electives and 10 professional internships. Details: idiomas.mxl.uabc.mx or call 686-689-0825.","fr":"Pour diplomer en Traduction (LT) il faut 349 credits: 237 obligatoires, 102 optionnels et 10 de stages. Details: idiomas.mxl.uabc.mx ou 686-689-0825."}),
 (["carrera","tsu","tecnico","programas","traduc","translation","traduction"], {"es":"La Facultad ofrece Licenciaturas en Ensenanza de Lenguas (LEL) y Traduccion (LT), y el TSU. Consulta idiomas.mxl.uabc.mx o 686-689-0825.","en":"The Faculty offers Language Teaching (LEL) and Translation (LT) degrees plus a TSU. See idiomas.mxl.uabc.mx or call 686-689-0825.","fr":"La Faculte offre les licences LEL et LT et un TSU. Voir idiomas.mxl.uabc.mx ou 686-689-0825."}),
 (["frances","french","francais","ingles","english","anglais","study","estudiar","etud","curso","cours","cec","horario"], {"es":"El CEC ofrece cursos de ingles, frances, aleman, italiano, portugues, ruso, mandarin, japones, coreano y espanol, en formatos semanal, sabatino, intensivo e intersemestral. Grupos en cecuabc.com. Informes: recepcionmxl@uabc.edu.mx o 686 841-82-91 ext. 300.","en":"The CEC offers English, French, German, Italian, Portuguese, Russian, Mandarin, Japanese, Korean and Spanish courses. Groups at cecuabc.com. Info: recepcionmxl@uabc.edu.mx or 686 841-82-91 ext. 300.","fr":"Le CEC propose des cours d'anglais, francais, allemand, italien, portugais, russe, mandarin, japonais, coreen et espagnol. Groupes sur cecuabc.com. Infos: recepcionmxl@uabc.edu.mx ou 686 841-82-91 poste 300."}),
 (["admision","requisito","admission"], {"es":"Para ingresar: 1) concluir bachillerato, 2) certificado/acta/CURP, 3) registro en el portal (agosto y enero), 4) Examen de Seleccion. No se requiere ingles avanzado. Fechas: admision.uabc.mx.","en":"To enter: 1) finish high school, 2) certificate/acta/CURP, 3) register (August and January), 4) Selection Exam. No advanced English needed. Dates: admision.uabc.mx.","fr":"Pour entrer: 1) terminer le lycee, 2) certificat/acta/CURP, 3) s'inscrire (aout et janvier), 4) Examen de Selection. Dates: admision.uabc.mx."}),
 (["que haces","what do you do","ayudar","help","sirves","puedes hacer"], {"es":"Te informo sobre creditos, CEC, admision, carreras, avisos y a QUIEN acudir por cada tema, en espanol, ingles o frances: te leo o te escucho.","en":"I cover credits, CEC, admission, degrees, notices and WHO to contact for each topic, in Spanish, English or French: I read you or listen to you.","fr":"Je couvre credits, CEC, admission, licences, avis et QUI contacter, en espagnol, anglais ou francais: je vous lis ou vous ecoute."}),
]

def _limpiar_doc(t):
    out = []
    for ln in (t or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("===") or s.startswith("DOCUMENTO"): continue
        out.append(s)
    return "\n".join(out)
def _tokens(t): return set(re.findall(r"[a-zaeiou$0-9]+", (t or "").lower()))
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
    if any(k in p for k in ("semana","evento","hoy","manana","pronto","avisos","hay")):
        fres = [t for t in docs.values() if any(hoy <= f <= hor for f in _fechas_doc(t))][:2]
        if fres: return "Avisos oficiales recientes:\n\n" + "\n\n".join(t[:500] for t in fres)
    qt = _tokens(preg)
    sc = sorted(((len(qt & _tokens(t)), t) for t in docs.values()), reverse=True)
    if sc and sc[0][0] >= 3: return "Segun la informacion oficial: " + sc[0][1][:600]
    return ""
def sistema_prompt(ctx, rol="externo"):
    extra = " El usuario es comunidad UABC: puedes incluir avisos internos de clases/tareas. " if rol == "interno" else " El usuario es publico general: NO reveles info interna de clases/tareas. "
    return (f"Hoy es {fecha_hoy_es()}. Eres UABCBot Idiomas de la Facultad de Idiomas UABC Mexicali. "
      "Responde en el idioma de la pregunta, conciso. Si preguntan COSTOS da la cifra exacta disponible. "
      "NUNCA repitas la pregunta. FECHAS: primero eventos de los proximos 14 dias. "
      "REGLAS: responde solo lo preguntado; no copies nombres de archivo ni ===; reformula. "
      "Si un tema tiene responsable, mencionalo para atender directo sin tramites. "
      "Si no aparece, sugiere 686-689-0825 / idiomas.mxl@uabc.edu.mx. " + extra + f"\nINFORMACION:\n{ctx}")

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
    errs.append("Groq vision no disp.")
    t=llamar_vision(OR_URL,OR_KEY,["meta-llama/llama-3.2-90b-vision-instruct:free"],b64,mime,PROMPT_POSTER)
    if t: return t,""
    errs.append("OpenRouter vision no disp.")
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
    return not (t.startswith("Error") or t.startswith("Avisos") or t.startswith("Segun") or t.startswith("Sobre") or len(t)<60 or "ayudarte hoy" in low or "no esta en el contexto" in low or "===" in t or "documento " in low or len(t)>900)
def _hash(c,s): return hashlib.sha256((s+c).encode()).hexdigest()

def responder(pregunta, historial, lang_pref="auto", rol="externo"):
    p=(pregunta or "").lower()
    lang = lang_pref if lang_pref in ("es","en","fr") else detectar_idioma(pregunta)
    for e in cargar_catalogo():
        if any(k in p for k in e["kw"]):
            return resp_catalogo(e), lang
    if not any(k in p for k in ("cuanto","cuanto","cuesta","costo","precio","inscri")):
        for claves,trad in MEMORIA_OFICIAL:
            if any(k in p for k in claves): return trad.get(lang,trad["es"]),lang
    clave=p.strip()[:120]+f"|{rol}"
    cache=_cargar_cache()
    if clave in cache: return cache[clave][0],cache[clave][1]
    sp=sistema_prompt(cargar_contexto(pregunta,rol),rol)
    suf={"es":" (Responde en espanol, conciso.)","en":" (Answer in English, concise.)","fr":" (Reponds en francais, concis.)"}[lang]
    pf=pregunta+suf
    hist=[{"role":("user" if m["role"]=="user" else "assistant"),"content":m["content"]} for m in (historial or []) if isinstance(m,dict) and isinstance(m.get("content"),str)]
    texto=llamar_openai(sp,hist,pf,GROQ_URL,GROQ_KEY,["llama-3.1-70b-versatile","llama-3.1-8b-instant"])
    if not _es_valida(texto): texto=llamar_gemini(cliente_gemini,sp,hist,pf)
    if not _es_valida(texto): texto=llamar_gemini(cliente_gemini2,sp,hist,pf)
    if not _es_valida(texto): texto=llamar_openai(sp,hist,pf,OR_URL,OR_KEY,["deepseek/deepseek-v4-flash"])
    if not _es_valida(texto):
        fb=respuesta_de_documentos(pregunta,rol)
        if fb: return fb,lang
    if not _es_valida(texto): texto="Motores saturados. Intenta en unos segundos."
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
                r=c.models.generate_content(model="gemini-2.5-flash",contents=[gtypes.Part(inline_data=gtypes.Blob(data=ab,mime_type=mime)),"Transcribe este audio (es/en/fr). Solo la transcripcion."])
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

FAQ=[(["credito","titular","titul"],"Cuantos creditos necesito para titularme en Traduccion?"),(["costo","cuesta","precio","inscri"],"Cuanto cuesta inscribirme a las clases de ingles?"),(["horario","cec"],"Cuales son los horarios del CEC?"),(["admision","requisito"],"Cuales son los requisitos de admision?"),(["carrera","tsu","tecnico"],"Que carreras y programas tecnicos ofrece?")]
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
        return "Respaldo listo." if q.status_code in (200,201) else "No respaldado."
    except Exception: return "No respaldado."
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
        if texto==CLAVE_ADMIN: state["active"]=True; return "Acceso concedido. SALIR para cerrar.",None,state
        return "Clave incorrecta.",None,state
    if state.get("active"):
        if texto.upper()=="SALIR": state["active"]=False; return "Cerrado.",None,state
        n,r=guardar_aviso(texto); return f"Publicado. {r}",None,state
    if "administraci" in texto.lower(): state["pending"]=True; return "Escribe la clave.",None,state
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
    if len(u)<3 or len(c)<4: return {"ok":False,"error":"Usuario 3 y clave 4."}
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
    except Exception as e: r=f"Error: {type(e).__name__}"; a=None; s=st; l="es"
    return {"reply":r,"audio":a,"state":s,"lang":l}
@app.post("/api/voice")
async def api_voice(audio:UploadFile=File(...),hist:str=Form("[]"),state:str=Form("{}"),lang:str=Form("auto"),rol:str=Form("externo")):
    data=await audio.read(); texto,_=transcribir(data)
    if not texto: return {"texto":"","reply":"No escuche bien.","audio":None,"state":state,"lang":"es"}
    st=json.loads(state)
    if not (st.get("active") or st.get("pending")): log_uso(texto,lang,"voz")
    r,l,s=router(texto,json.loads(hist),st,lang,rol); a=await producir_audio(r,l)
    return {"texto":texto,"reply":r,"audio":a,"state":s,"lang":l}
@app.post("/api/voice_note")
async def voice_note(audio:UploadFile=File(...),categoria:str=Form("Avisos"),responsable:str=Form("")):
    data=await audio.read(); texto,_=transcribir(data)
    if not texto: return {"estado":"No escuche la nota."}
    n,r=guardar_aviso(texto,categoria,responsable); return {"estado":f"Nota publicada: {n}. {r}"}
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
    if d.get("clave")!=CLAVE_ADMIN: return {"error":"Clave incorrecta"}
    lines=leer_uso(); hoy=datetime.now().strftime("%Y-%m-%d")
    c=Counter(normalizar_faq(l["texto"]) for l in lines if l.get("texto")); idi=Counter(l.get("lang","auto") for l in lines)
    pend=[]
    for fn in sorted(os.listdir(FEEDBACK),reverse=True)[:15]:
        try:
            txt=open(os.path.join(FEEDBACK,fn),encoding="utf-8").read()
            a=re.search(r"Area: (.+?) \|",txt); pg=re.search(r"PREGUNTA: (.+)",txt)
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
    cont=f"=== Feedback {ts} | Area: {area} | Reenviar a: {AREAS_RESP.get(area,AREAS_RESP['Otro'])} ===\nCAPTURA: {capurl or 'no disp.'}\nPREGUNTA: {d.get('pregunta','')}\nRESPUESTA: {d.get('respuesta','')}\nCOMENTARIO: {d.get('comentario','')}\n"
    open(os.path.join(FEEDBACK,ts+".txt"),"w",encoding="utf-8").write(cont); github_subir(f"feedback/{ts}.txt",cont.encode())
    return {"ok":True,"captura":capurl}
@app.get("/captura/{n}")
async def captura(n:str): return FileResponse(os.path.join(CAPTURAS,n),media_type="image/png")
@app.get("/api/feedback/list")
async def fb_list(clave:str=""):
    if clave!=CLAVE_ADMIN: return {"items":["Clave incorrecta"]}
    out=[]
    for fn in sorted(os.listdir(FEEDBACK),reverse=True)[:10]:
        try: out.append(open(os.path.join(FEEDBACK,fn),encoding="utf-8").read())
        except Exception: pass
    return {"items":out or ["Sin feedbacks. "]}
@app.post("/api/upload")
async def api_upload(archivo:UploadFile=File(None),categoria:str=Form("Avisos"),vigencia:str=Form(""),reemplazar:str=Form("0"),texto_manual:str=Form(""),responsable:str=Form("")):
    texto=texto_manual.strip()
    if archivo is not None: nom=archivo.filename or "doc.txt"; ext=os.path.splitext(nom)[1].lower(); data=await archivo.read()
    else: nom="nota_manual.txt"; ext=".txt"; data=b""
    if ext in EXT_IMG:
        mime="image/png" if ext==".png" else "image/jpeg"
        if not texto: texto,err=extraer_imagen(data,mime)
        else: err=""
        if not texto: return {"estado":f"Vision no disp. ({err}). Pega el texto."}
        iname=str(uuid.uuid4())+ext; open(os.path.join(IMGS,iname),"wb").write(data); texto+=f"\nPoster: /img/{iname}"
    elif data:
        tmp=os.path.join(BASE,"tmp_"+nom); open(tmp,"wb").write(data); texto=extraer_texto(tmp,nom) or texto; os.remove(tmp)
    if not texto: return {"estado":"Elige archivo o pega texto."}
    if reemplazar=="1":
        for fn in list(os.listdir(CARPETA)):
            if fn.endswith(f"_{categoria}.txt"): os.remove(os.path.join(CARPETA,fn)); github_borrar(f"datos_bot/{fn}")
    nuevo,resp=guardar_aviso(texto,categoria,responsable)
    return {"estado":f"Guardado {nuevo} (Responsable: {responsable or 'sin asignar'}). {resp}"}
@app.post("/api/delete")
async def api_delete(req:Request):
    d=await req.json()
    if d.get("clave")!=CLAVE_ADMIN: return {"estado":"Clave incorrecta"}
    n=(d.get("nombre") or "").strip(); r=os.path.join(CARPETA,n)
    if os.path.exists(r): os.remove(r); github_borrar(f"datos_bot/{n}"); return {"estado":f"{n} eliminado."}
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
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UABCBot Idiomas</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
body{background:#eef1f4;min-height:100vh}
.app{max-width:1000px;margin:0 auto;height:100vh;display:flex;flex-direction:column;background:#fff;box-shadow:0 0 40px rgba(0,0,0,0.1)}
.header{background:linear-gradient(135deg,#00684a,#00855f);color:#fff;padding:16px 20px;display:flex;align-items:center;gap:12px}
.header img{width:44px;height:44px;background:#fff;border-radius:10px;padding:2px}
.header h1{font-size:18px;font-weight:600}
.header p{font-size:11px;opacity:0.9}
.controls{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap;align-items:center}
.lang-btn{padding:5px 10px;border-radius:20px;border:1px solid rgba(255,255,255,0.4);background:transparent;color:#fff;cursor:pointer;font-size:11px;font-weight:500;transition:all 0.2s}
.lang-btn.active{background:#f7941d;border-color:#f7941d;color:#fff}
.icon-btn{width:34px;height:34px;border-radius:50%;border:none;background:rgba(255,255,255,0.15);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background 0.2s}
.icon-btn:hover{background:rgba(255,255,255,0.3)}
.icon-btn svg{width:18px;height:18px;fill:currentColor}
.messages{flex:1;overflow-y:auto;padding:20px;background:#f8f9fa;display:flex;flex-direction:column;gap:12px}
.welcome{background:#fff;padding:20px;border-radius:16px;box-shadow:0 2px 12px rgba(0,0,0,0.06);margin-bottom:8px}
.welcome h2{color:#00684a;font-size:18px;margin-bottom:8px}
.welcome p{color:#555;font-size:14px;line-height:1.5;margin-bottom:16px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{padding:10px 16px;background:#fff;color:#00684a;border:2px solid #00855f;border-radius:24px;cursor:pointer;font-size:13px;font-weight:500;transition:all 0.2s}
.chip:hover{background:#00855f;color:#fff;transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,133,95,0.3)}
.msg{max-width:80%;padding:12px 16px;border-radius:16px;font-size:14px;line-height:1.5;animation:fadeIn 0.3s}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.msg.user{align-self:flex-end;background:#00855f;color:#fff;border-bottom-right-radius:4px}
.msg.bot{align-self:flex-start;background:#fff;color:#1a1a1a;box-shadow:0 2px 8px rgba(0,0,0,0.08);border-bottom-left-radius:4px}
.msg audio{max-width:240px;margin-top:6px}
.input-area{padding:16px 20px;background:#fff;border-top:1px solid #e5e7eb;display:flex;gap:10px;align-items:center}
.input-field{flex:1;padding:12px 18px;border:2px solid #e5e7eb;border-radius:24px;font-size:14px;outline:none;transition:border-color 0.2s}
.input-field:focus{border-color:#00855f}
.send-btn{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#00684a,#00855f);border:none;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:transform 0.2s}
.send-btn:hover{transform:scale(1.05)}
.send-btn svg{width:20px;height:20px;fill:currentColor}
.toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:12px 20px;border-radius:10px;color:#fff;font-size:13px;z-index:1000;animation:slideIn 0.3s}
@keyframes slideIn{from{opacity:0;transform:translateX(-50%) translateY(-10px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
.toast.ok{background:#00855f}.toast.err{background:#d32f2f}.toast.warn{background:#f7941d}
.panel{display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#fff;padding:24px;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:500px;width:90%;max-height:80vh;overflow-y:auto;z-index:200}
.panel.show{display:block}
.panel-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:150}
.panel-overlay.show{display:block}
.panel h3{color:#00684a;margin-bottom:12px;font-size:16px}
.panel input,.panel select,.panel textarea{width:100%;padding:10px 14px;margin-bottom:10px;border:2px solid #e5e7eb;border-radius:10px;font-size:13px;outline:none}
.panel input:focus,.panel select:focus,.panel textarea:focus{border-color:#00855f}
.panel button{padding:10px 18px;background:#00855f;color:#fff;border:none;border-radius:10px;cursor:pointer;font-size:13px;margin-right:6px;margin-bottom:6px}
.panel button:hover{background:#00684a}
.close-x{position:absolute;top:12px;right:12px;width:32px;height:32px;border-radius:50%;border:none;background:#f3f4f6;cursor:pointer;font-size:16px;color:#666}
@media(max-width:768px){.app{height:100vh}.header h1{font-size:15px}.msg{max-width:90%}}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <img src="/logo.png" alt="logo">
    <div><h1>UABCBot Idiomas</h1><p>Facultad de Idiomas UABC Mexicali</p></div>
    <div class="controls">
      <button class="lang-btn active" onclick="setLang('auto')">AUTO</button>
      <button class="lang-btn" onclick="setLang('es')">ES</button>
      <button class="lang-btn" onclick="setLang('en')">EN</button>
      <button class="lang-btn" onclick="setLang('fr')">FR</button>
      <button class="icon-btn" onclick="changeFontSize(-0.1)" title="Reducir letra"><svg viewBox="0 0 24 24"><path d="M19 13H5v-2h14v2z"/></svg></button>
      <button class="icon-btn" onclick="changeFontSize(0.1)" title="Aumentar letra"><svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg></button>
      <button class="icon-btn" onclick="toggleFullscreen()" title="Pantalla completa"><svg viewBox="0 0 24 24"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg></button>
      <button class="icon-btn" onclick="togglePanel()" title="Panel"><svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1115.6 12 3.611 3.611 0 0112 15.6z"/></svg></button>
    </div>
  </div>
  <div class="messages" id="messages"></div>
  <div class="input-area">
    <button class="icon-btn" onclick="toggleVoice()" title="Voz" style="background:#00855f"><svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg></button>
    <input type="text" class="input-field" id="input" placeholder="Escribe tu pregunta..." onkeypress="if(event.key==='Enter')sendMessage()">
    <button class="send-btn" onclick="sendMessage()" title="Enviar"><svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>
    <button class="icon-btn" onclick="toggleFeedback()" title="Reportar" style="background:#d32f2f"><svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></button>
  </div>
</div>
<div class="panel-overlay" id="overlay" onclick="togglePanel()"></div>
<div class="panel" id="panel">
  <button class="close-x" onclick="togglePanel()">X</button>
  <h3>Panel de Administracion</h3>
  <input type="password" id="adminKey" placeholder="Clave de acceso">
  <button onclick="unlockPanel()">Entrar</button>
  <div id="adminContent" style="display:none">
    <h3>Subir Aviso</h3>
    <select id="categoria"><option>Avisos</option><option>Eventos</option><option>Horarios</option><option>Examenes</option><option>Clases</option></select>
    <input type="text" id="responsable" placeholder="Responsable">
    <textarea id="textoAviso" rows="4" placeholder="Texto del aviso..."></textarea>
    <button onclick="uploadNotice()">Publicar</button>
    <button onclick="showReport()">Ver Reporte</button>
    <div id="reporte" style="white-space:pre-wrap;background:#f8f9fa;padding:12px;border-radius:8px;margin-top:10px;font-size:12px"></div>
  </div>
</div>
<script>
let hist=[],state={pending:false,active:false},langPref="auto",lastP="",lastR="",fontScale=1,rec=null;
const messages=document.getElementById('messages');
const input=document.getElementById('input');

const W={es:"Hola! Soy UABCBot Idiomas de la Facultad de Idiomas UABC Mexicali. Te atiendo en espanol, ingles o frances: te leo o te escucho. Como puedo ayudarte hoy?",en:"Hi! I am UABCBot Idiomas of the UABC Faculty of Languages in Mexicali. I serve you in Spanish, English or French: I read you or listen to you. How can I help you today?",fr:"Bonjour! Je suis UABCBot Idiomas de la Faculte de Langues de l'UABC a Mexicali. Je vous aide en espagnol, anglais ou francais: je vous lis ou vous ecoute. Comment puis-je vous aider?"};
const S={
  es:[{q:"Cuantos creditos necesito para titularme en Traduccion?",t:"Creditos para titularme"},{q:"Cuanto cuesta inscribirme a las clases de ingles?",t:"Costo clases ingles"},{q:"Cuales son los requisitos de admision?",t:"Requisitos admision"},{q:"Que carreras y programas tecnicos ofrece la Facultad?",t:"Carreras y TSU"}],
  en:[{q:"How many credits do I need to graduate from Translation?",t:"Credits to graduate"},{q:"How much does it cost to enroll in English classes?",t:"English class cost"},{q:"What are the admission requirements?",t:"Admission requirements"},{q:"What degrees and programs does the Faculty offer?",t:"Degrees and TSU"}],
  fr:[{q:"Combien de credits pour diplomer en Traduction?",t:"Credits pour diplomer"},{q:"Combien coutent les cours d'anglais?",t:"Cout cours anglais"},{q:"Quelles sont les conditions d'admission?",t:"Conditions admission"},{q:"Quelles licences et programmes offre la Faculte?",t:"Licences et TSU"}]
};

function setLang(l){langPref=l;document.querySelectorAll('.lang-btn').forEach(b=>b.classList.remove('active'));event.target.classList.add('active');loadWelcome()}
function loadWelcome(){const L=langPref==='auto'?'es':langPref;const w=W[L]||W.es;const sug=S[L]||S.es;let chips=sug.map(s=>'<button class="chip" onclick="sendQ(\''+s.q.replace(/'/g,"\\'")+'\')">'+s.t+'</button>').join('');
messages.innerHTML='<div class="welcome"><h2>UABCBot Idiomas</h2><p>'+w+'</p><div class="chips">'+chips+'</div></div>'}
function sendQ(q){input.value=q;sendMessage()}
function sendMessage(){const msg=input.value.trim();if(!msg)return;hist.push({role:'user',content:msg});addMsg(msg,'user');input.value='';lastP=msg;thinking();
fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({msg,hist:hist.slice(-7),state,lang:langPref,rol:'externo'})})
.then(r=>r.json()).then(d=>{removeThink();state=d.state;lastR=d.reply;hist.push({role:'assistant',content:d.reply});addMsg(d.reply,'bot')}).catch(e=>{removeThink();addMsg('Error: '+e,'bot')})}
function addMsg(text,role){const div=document.createElement('div');div.className='msg '+role;div.textContent=text;messages.appendChild(div);messages.scrollTop=messages.scrollHeight}
function thinking(){const div=document.createElement('div');div.className='msg bot';div.id='thinking';div.textContent='Pensando...';messages.appendChild(div);messages.scrollTop=messages.scrollHeight}
function removeThink(){const t=document.getElementById('thinking');if(t)t.remove()}
function changeFontSize(d){fontScale=Math.max(0.8,Math.min(1.6,fontScale+d));document.documentElement.style.setProperty('--fs',fontScale);toast('Letra: '+Math.round(fontScale*100)+'%','ok')}
function toggleFullscreen(){if(!document.fullscreenElement)document.documentElement.requestFullscreen();else document.exitFullscreen()}
function togglePanel(){document.getElementById('panel').classList.toggle('show');document.getElementById('overlay').classList.toggle('show')}
function unlockPanel(){const k=document.getElementById('adminKey').value;fetch('/api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clave:k})}).then(r=>r.json()).then(d=>{if(d.ok){document.getElementById('adminContent').style.display='block';toast('Panel abierto','ok')}else toast('Clave incorrecta','err')})}
function uploadNotice(){const cat=document.getElementById('categoria').value;const resp=document.getElementById('responsable').value;const txt=document.getElementById('textoAviso').value;
const fd=new FormData();fd.append('categoria',cat);fd.append('responsable',resp);fd.append('texto_manual',txt);
fetch('/api/upload',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{toast(d.estado,'ok');document.getElementById('textoAviso').value=''}).catch(e=>toast('Error: '+e,'err'))}
function showReport(){fetch('/api/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clave:document.getElementById('adminKey').value})}).then(r=>r.json()).then(d=>{let t='Total: '+d.total+' - Hoy: '+d.hoy+'\\n';d.top.forEach((x,i)=>t+=(i+1)+'. '+x[0]+' ('+x[1]+')\\n');document.getElementById('reporte').innerText=t}).catch(e=>toast('Error: '+e,'err'))}
function toast(m,t){const div=document.createElement('div');div.className='toast '+t;div.textContent=m;document.body.appendChild(div);setTimeout(()=>div.remove(),3000)}
function toggleVoice(){toast('Funcion de voz disponible proximamente','warn')}
function toggleFeedback(){toast('Reportar respuesta disponible proximamente','warn')}
loadWelcome();
</script>
</body>
</html>
"""

@app.get("/")
async def inicio(): return HTMLResponse(PAGINA)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
