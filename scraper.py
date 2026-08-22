"""
scraper.py — Barrido de páginas oficiales de la Facultad de Idiomas
Uso: python scraper.py
Guarda los textos en datos_bot/ con fecha de actualización.
"""
import os
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE, "datos_bot")
os.makedirs(CARPETA, exist_ok=True)

PAGINAS = {
    "PracticasProfesionales": "https://idiomas.mxl.uabc.mx/practicas-profesionales/",
    "Admision": "https://idiomas.mxl.uabc.mx/admision/",
    "CEC": "https://idiomas.mxl.uabc.mx/cec/",
    "Titulacion": "https://idiomas.mxl.uabc.mx/titulacion/",
    "Egresados": "https://idiomas.mxl.uabc.mx/egresados/",
    "Posgrado": "https://idiomas.mxl.uabc.mx/posgrado/",
    "OfertaEducativa": "https://idiomas.mxl.uabc.mx/oferta-educativa/",
    "Inicio": "https://idiomas.mxl.uabc.mx/",
}

HEADERS = {"User-Agent": "UABCBot-Scraper/1.0"}

def limpiar_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    texto = soup.get_text(separator="\n", strip=True)
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    return "\n".join(lineas)

def barrer():
    hoy = datetime.now().strftime("%Y%m%d")
    resultados = []
    for nombre, url in PAGINAS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                print(f"️ {nombre}: HTTP {r.status_code}")
                continue
            texto = limpiar_html(r.text)
            if len(texto) < 100:
                print(f"⚠️ {nombre}: texto muy corto")
                continue
            archivo = f"{hoy}_{nombre}.txt"
            cabecera = f"=== {nombre} | Barrido: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Fuente: {url} ===\n"
            with open(os.path.join(CARPETA, archivo), "w", encoding="utf-8") as f:
                f.write(cabecera + texto)
            resultados.append((nombre, len(texto)))
            print(f"✅ {nombre}: {len(texto)} chars")
            time.sleep(1)
        except Exception as e:
            print(f"❌ {nombre}: {e}")
    return resultados

if __name__ == "__main__":
    print(f"🕷️ Barrido iniciado {datetime.now()}")
    res = barrer()
    print(f"\n📊 {len(res)} páginas actualizadas.")
