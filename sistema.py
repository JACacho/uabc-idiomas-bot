import os
import re
import json
import time
import asyncio
import tempfile
import requests
from datetime import datetime
from google.genai import types

try:
    from config import client as cliente_gemini
except Exception:
    cliente_gemini = None

BASE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(BASE, "Manual_Aspirantes_Idiomas_UABC.txt")
CARPETA = os.path.join(BASE, "datos_bot")
CACHE = os.path.join(BASE, "cache.json")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")

VOCES = {"es": "es-MX-DaliaNeural", "en": "en-US-AriaNeural", "fr": "fr-FR-DeniseNeural"}

MEMORIA_OFICIAL = [
    (["credito", "titular"], {
        "es": "Para titularte en la Licenciatura en Traducción (LT) de la Facultad de Idiomas de la UABC necesitas un total de 349 créditos: 237 de materias obligatorias, 102 de materias optativas y 10 de prácticas profesionales. Para más detalles consulta idiomas.mxl.uabc.mx o llama al 686-689-0825.",
        "en": "To graduate from the Translation Bachelor's (LT) at the UABC Faculty of Languages you need 349 credits: 237 mandatory, 102 electives and 10 professional internships. Details at idiomas.mxl.uabc.mx or call 686-689-0825.",
        "fr": "Pour obtenir votre diplôme en Traduction (LT) à la Faculté de Langues de l'UABC, il faut 349 crédits : 237 obligatoires, 102 optionnels et 10 de stages. Détails sur idiomas.mxl.uabc.mx ou au 686-689-0825."}),
    (["frances", "francés", "french", "français", "ingles", "inglés", "english", "study", "estudiar", "curso", "cec", "horario"], {
        "es": "El Centro de Enseñanza de Lenguas (CEC) ofrece cursos de inglés, francés, alemán, italiano, portugués, ruso, chino mandarín, japonés, coreano y español para extranjeros, en formatos semanal, sabatino, intensivo e intersemestral, con horarios matutinos, vespertinos y nocturnos. Los grupos de cada periodo se publican en cecuabc.com. Informes: recepcionmxl@uabc.edu.mx o al 686 841-82-91 ext. 300.",
        "en": "The Language Teaching Center (CEC) offers courses in English, French, German, Italian, Portuguese, Russian, Mandarin, Japanese, Korean and Spanish for foreigners, in weekly, Saturday, intensive and inter-semester formats, morning, afternoon and evening. Groups are published each term at cecuabc.com. Info: recepcionmxl@uabc.edu.mx or 686 841-82-91 ext. 300.",
        "fr": "Le Centre d'Enseignement des Langues (CEC) propose des cours d'anglais, de français, d'allemand, d'italien, de portugais, de russe, de mandarin, de japonais, de coréen et d'espagnol pour étrangers, en formats hebdomadaire, samedi, intensif et intersemestriel, matin, après-midi et soir. Les groupes sont publiés chaque semestre sur cecuabc.com. Infos : recepcionmxl@uabc.edu.mx ou 686 841-82-91 poste 300."}),
    (["admision", "requisito"], {
        "es": "Para ingresar a la Facultad de Idiomas necesitas: 1) concluir el bachillerato con promedio aprobatorio, 2) certificado de bachillerato, acta de nacimiento y CURP, 3) registrarte en el portal de admisiones cuando abra la convocatoria (agosto y enero), y 4) presentar el Examen de Selección institucional. No se requiere inglés avanzado: la Facultad te forma desde cero. Fechas en admision.uabc.mx.",
        "en": "To enter the Faculty of Languages you need: 1) finish high school with a passing average, 2) high school certificate, birth certificate and CURP, 3) register on the admissions portal when the call opens (August and January), and 4) take the institutional Selection Exam. Advanced English is not required: the Faculty trains you from zero. Dates at admision.uabc.mx.",
        "fr": "Pour entrer à la Faculté de Langues : 1) terminer le lycée avec une moyenne suffisante, 2) certificat de lycée, acte de naissance et CURP, 3) s'inscrire sur le portail d'admission quand l'appel ouvre (août et janvier), et 4) passer l'Examen de Sélection institutionnel. L'anglais avancé n'est pas requis : la Faculté vous forme depuis zéro. Dates sur admision.uabc.mx."}),
    (["carrera", "tsu", "tecnico", "técnico", "programas"], {
        "es": "La Facultad de Idiomas ofrece dos licenciaturas: Enseñanza de Lenguas (LEL) y Traducción (LT), además del Técnico Superior Universitario (TSU), una opción con enfoque práctico y rápida salida al campo laboral. Consulta la convocatoria vigente en idiomas.mxl.uabc.mx o llama al 686-689-0825.",
        "en": "The Faculty of Languages offers two bachelor's degrees: Language Teaching (LEL) and Translation (LT), plus a Higher University Technician (TSU) program with a practical focus and quick entry to the job market. Check the current call at idiomas.mxl.uabc.mx or call 686-689-0825.",
        "fr": "La Faculté de Langues propose deux licences : Enseignement des Langues (LEL) et Traduction (LT), ainsi qu'un Technicien Supérieur Universitaire (TSU), option pratique avec insertion rapide sur le marché du travail. Consultez l'appel en cours sur idiomas.mxl.uabc.mx ou appelez le 686-689-0825."}),
    (["que haces", "what do you do", "ayudar", "help", "sirves", "puedes hacer"], {
        "es": "Puedo informarte sobre créditos y planes de estudio, cursos y horarios del CEC, requisitos de admisión, carreras y TSU, y avisos o fechas oficiales de la Facultad de Idiomas de la UABC en Mexicali, en español, inglés o francés, por texto o por voz. ¿Qué te gustaría saber?",
        "en": "I can help you with credits and study plans, CEC courses and schedules, admission requirements, degrees and TSU, and official notices and dates of the UABC Faculty of Languages in Mexicali, in Spanish, English or French, by text or voice. What would you like to know?",
        "fr": "Je peux vous renseigner sur les crédits et plans d'études, les cours et horaires du CEC, les conditions d'admission, les licences et le TSU, ainsi que les avis et dates officielles de la Faculté de Langues de l'UABC à Mexicali, en espagnol, anglais ou français, par texte ou par voix. Que souhaitez-vous savoir ?"}),
]

def detectar_idioma(texto):
    t = (texto or "").lower()
    fr = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplôme", "traduction", "salut", "crédits", "je", "étudier", "français", "francais", "aime", "voudrais", "quel", "quelle", "les", "des", "est"]
    en = ["hello", "thank", "how", "many", "credits", "degree", "translation", "what", "when", "where", "i", "would", "like", "to", "study", "french", "english", "do", "you", "for", "me", "is", "are", "the", "my", "can", "help"]
    hf = sum(1 for w in fr if re.search(r"\b" + w + r"\b", t))
    he = sum(1 for w in en if re.search(r"\b" + w + r"\b", t))
    if hf >= 2 and hf > he:
        return "fr"
    if he >= 2 and he > hf:
        return "en"
    return "es"

def _limpiar_doc(texto):
    lineas = []
    for ln in (texto or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("===") or s.startswith("DOCUMENTO") or s.startswith("🖼️"):
            continue
        lineas.append(s)
    return "\n".join(lineas)

def _tokens(t):
    return set(re.findall(r"[a-záéíóúñü]+", (t or "").lower()))

def cargar_contexto(pregunta):
    partes = []
    try:
        with open(MANUAL, encoding="utf-8", errors="ignore") as f:
            partes.append(_limpiar_doc(f.read()))
    except Exception:
        pass
    qt = _tokens(pregunta)
    docs = []
    if os.path.isdir(CARPETA):
        for fn in sorted(os.listdir(CARPETA)):
            if fn.endswith(".txt"):
                try:
                    with open(os.path.join(CARPETA, fn), encoding="utf-8", errors="ignore") as f:
                        texto = _limpiar_doc(f.read())
                except Exception:
                    continue
                score = len(qt & _tokens(texto))
                docs.append((score, texto))
    docs.sort(key=lambda x: x[0], reverse=True)
    for score, texto in docs[:2]:
        if score >= 2:
            partes.append(texto)
    return "\n\n".join(partes)[:9000]

def sistema_prompt(contexto):
    hoy = datetime.now().strftime("%A %d de %B de %Y")
    return (
        f"Hoy es {hoy}. Eres UABCBot Idiomas, asistente virtual de la Facultad de Idiomas de la UABC en Mexicali. "
        "Responde SIEMPRE en el idioma de la pregunta y en párrafos naturales y concisos (máximo ~120 palabras salvo que pidan detalle). "
        "REGLAS DE ORO: responde ÚNICAMENTE a la pregunta del usuario; NUNCA reproduzcas el contexto como lista de preguntas y respuestas; "
        "NUNCA copies nombres de archivo, encabezados con ===, ni palabras como DOCUMENTO o CONTEXTO; reformula con tus palabras y usa solo datos disponibles. "
        "Si la información no aparece, sugiere contactar a la Facultad: tel. 686-689-0825, idiomas.mxl@uabc.edu.mx, idiomas.mxl.uabc.mx. "
        f"\nINFORMACIÓN DISPONIBLE:\n{contexto}"
    )

def llamar_gemini(sp, hist, pregunta):
    if not cliente_gemini:
        return None
    try:
        contents = []
        for m in hist:
            contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": pregunta}]})
        r = cliente_gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=sp, temperature=0.1),
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
                timeout=20,
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
    return not (texto.startswith("⚠️") or "no está en el contexto" in t or "===" in texto or "documento " in t or "manual de conocimiento" in t or len(texto) > 900)

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
    suf = {"es": " (Responde en español, conciso.)", "en": " (Answer in English, concise.)", "fr": " (Réponds en français, concis.)"}[lang]
    pregunta_final = pregunta + suf
    hist = []
    for m in (historial or []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            hist.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
    texto = llamar_openai(sp, hist, pregunta_final, "https://api.groq.com/openai/v1/chat/completions", GROQ_KEY, ["llama-3.3-70b-versatile"])
    if not texto:
        texto = llamar_gemini(sp, hist, pregunta_final)
    if not texto:
        texto = llamar_openai(sp, hist, pregunta_final, "https://openrouter.ai/api/v1/chat/completions", OR_KEY, ["meta-llama/llama-3.3-70b-instruct:free"])
    if not texto:
        texto = "⚠️ Los motores de IA están saturados en este momento. Intenta de nuevo en unos segundos."
    texto = re.sub(r"^(\s*\[[^\]]{1,40}\]\s*)+", "", texto).strip()
    if _es_cacheable(texto):
        cache[clave] = [texto, lang]
        _guardar_cache(cache)
    return texto, lang

def transcribir_groq(data):
    if not GROQ_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("voz.webm", data, "audio/webm")},
            data={"model": "whisper-large-v3"},
            timeout=60,
        )
        return (r.json().get("text") or "").strip()
    except Exception:
        return ""

def transcribir(audio_bytes):
    if cliente_gemini:
        for modelo in ("gemini-2.5-flash", "gemini-2.0-flash"):
            for mime in ("audio/webm", "audio/wav", "audio/mp3", "audio/ogg"):
                try:
                    r = cliente_gemini.models.generate_content(
                        model=modelo,
                        contents=[
                            types.Part(inline_data=types.Blob(data=audio_bytes, mime_type=mime)),
                            "Transcribe textualmente este audio (español, inglés o francés). Devuelve solo la transcripción.",
                        ],
                    )
                    t = (r.text or "").strip()
                    if t:
                        return t, detectar_idioma(t)
                except Exception:
                    continue
    t = transcribir_groq(audio_bytes)
    if t:
        return t, detectar_idioma(t)
    return "", "es"

def extraer_imagen(data, mime="image/jpeg"):
    if not cliente_gemini:
        return ""
    for modelo in ("gemini-2.5-flash", "gemini-2.0-flash"):
        try:
            r = cliente_gemini.models.generate_content(
                model=modelo,
                contents=[
                    types.Part(inline_data=types.Blob(data=data, mime_type=mime)),
                    "Este es un anuncio o póster institucional. Extrae TODA la información útil (qué evento, quién invita, fecha, hora, lugar, contacto, requisitos) y devuélvela como texto claro en español, sin comentarios.",
                ],
            )
            t = (r.text or "").strip()
            if t:
                return t
        except Exception:
            continue
    return ""

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
