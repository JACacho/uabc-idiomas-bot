#!/usr/bin/env python3
# scraper_y_dedup.py - Scraper y deduplicador para el bot de la Facultad de Idiomas
# Extrae información de la página oficial y compara con datos_bot/ para detectar duplicados.
# No modifica ni borra archivos existentes.

import os
import time
import difflib
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# Importar funciones y datos del scraper existente para evitar duplicación de código
from scraper import limpiar_html, PAGINAS, HEADERS

def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATOS_BOT_DIR = os.path.join(BASE_DIR, "datos_bot")
    DATOS_SCRAPER_DIR = os.path.join(BASE_DIR, "datos_scraper")
    os.makedirs(DATOS_SCRAPER_DIR, exist_ok=True)

    # Timestamp para los nombres de archivo (YYYYMMDD_HHMM)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # Lista para almacenar las páginas scraped
    scraped_pages = []

    print(f"Iniciando scraping de {len(PAGINAS)} páginas...")
    for nombre, url in PAGINAS.items():
        # Saltar URLs externas (solo scraping del dominio oficial)
        if not url.startswith("https://idiomas.mxl.uabc.mx/"):
            print(f"⏭️  Saltando URL externa: {url}")
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"❌ Error al obtener {url}: {e}")
            continue

        # Parsear y limpiar HTML
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else "Sin título"
        # Eliminar etiquetas no deseadas
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        # Obtener texto principal
        main_text = soup.get_text(separator='\\n', strip=True)
        # Limpiar líneas en blanco múltiples
        lines = [line.strip() for line in main_text.splitlines() if line.strip()]
        cleaned_text = '\\n'.join(lines)

        # Guardar en datos_scraper/ con formato: YYYYMMDD_HHMM_web_<slug>.txt
        slug = nombre.lower()
        filename = f"{timestamp}_web_{slug}.txt"
        filepath = os.path.join(DATOS_SCRAPER_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)
        print(f"✅ Guardado: {filename}")

        scraped_pages.append({
            'filename': filename,
            'url': url,
            'title': title,
            'text': cleaned_text
        })

        # Esperar 2 segundos entre requests para no sobrecargar el servidor
        time.sleep(2)

    # Leer archivos existentes en datos_bot/
    existing_files = []
    for fname in os.listdir(DATOS_BOT_DIR):
        if fname.endswith('.txt'):
            path = os.path.join(DATOS_BOT_DIR, fname)
            existing_files.append({
                'filename': fname,
                'path': path
            })

    def get_main_text_from_existing(filepath):
        """Extrae el texto principal de un archivo de datos_bot/, eliminando líneas de cabecera que comienzan con '==='."""
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Filtrar líneas que son cabeceras (empiezan con '===')
        cleaned_lines = [line for line in lines if not line.strip().startswith('===')]
        return '\\n'.join(cleaned_lines).strip()

    # Preparar reporte
    report_lines = []
    report_lines.append("=== REPORTE DE DUPLICADOS ===")
    report_lines.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d')}")
    report_lines.append("")  # línea vacía

    duplicados = 0
    nuevos = 0
    conflictos = 0

    for page in scraped_pages:
        scraped_text = page['text']
        best_similarity = 0.0
        best_existing = None

        for existing in existing_files:
            existing_text = get_main_text_from_existing(existing['path'])
            if not existing_text:  # evitar textos vacíos
                continue
            similarity = difflib.SequenceMatcher(None, scraped_text, existing_text).ratio() * 100
            if similarity > best_similarity:
                best_similarity = similarity
                best_existing = existing['filename']

        # Clasificar según similitud
        if best_similarity >= 80:
            report_lines.append(f"[DUPLICADO] {page['filename']} → {best_existing} (similitud: {best_similarity:.0f}%)")
            duplicados += 1
        elif best_similarity >= 30:
            report_lines.append(f"[CONFLICTO] {page['filename']} → {best_existing} (similitud: {best_similarity:.0f}% - contenido diferente)")
            conflictos += 1
        else:
            report_lines.append(f"[NUEVO] {page['filename']}")
            nuevos += 1

    # Resumen
    report_lines.append("")
    report_lines.append("RESUMEN:")
    report_lines.append(f"- Total de páginas escaneadas: {len(scraped_pages)}")
    report_lines.append(f"- Duplicados detectados: {duplicados}")
    report_lines.append(f"- Contenido nuevo: {nuevos}")
    report_lines.append(f"- Conflictos (posible información contradictoria): {conflictos}")

    # Guardar reporte
    report_path = os.path.join(BASE_DIR, "reporte_duplicados.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\\n'.join(report_lines))

    print(f"\\n📄 Reporte guardado en: {report_path}")

if __name__ == "__main__":
    main()