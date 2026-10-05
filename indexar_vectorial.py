#!/usr/bin/env python3
# indexar_vectorial.py - Indexador vectorial para el bot de la Facultad de Idiomas
# Lee .txt de datos_bot/ y datos_scraper/, crea fragmentos y los guarda en ChromaDB.

import os
import time
import re
import chromadb
from sentence_transformers import SentenceTransformer

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS_BOT_DIR = os.path.join(BASE, "datos_bot")
DATOS_SCRAPER_DIR = os.path.join(BASE, "datos_scraper")
CHROMA_PATH = os.path.join(BASE, "chroma_db")
COLLECTION_NAME = "uabc_info"
EXCLUDE_FILE = "20261003_1954_web_traduccion.txt"  # duplicado confirmado

def chunk_text(text, target_len=500):
    """Divide el texto en fragmentos de ~target_len caracteres respetando párrafos."""
    # Primero separar por doble salto de línea (párrafos)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) <= target_len:
            chunks.append(para)
        else:
            # Párrafo muy largo: dividir por puntos seguidos de espacio o salto de línea
            # Mantener el punto al final de cada fragmento
            sentences = re.split(r'(?<=\.\s)', para)  # split after dot+space
            current = ""
            for sent in sentences:
                if len(current) + len(sent) <= target_len:
                    current += sent
                else:
                    if current:
                        chunks.append(current.strip())
                    current = sent
            if current:
                chunks.append(current.strip())
    # Filtrar fragmentos vacíos
    return [c for c in chunks if c]

def extract_category(filename):
    """Extrae la categoría del nombre de archivo."""
    # Quitar extensión
    name = filename[:-4] if filename.endswith('.txt') else filename
    # Quitar timestamp al inicio si existe (formato YYYYMMDD_HHMM_)
    if '_' in name and name[0].isdigit():
        # Asumimos que el timestamp está al principio y tiene al menos un _
        parts = name.split('_')
        # Si el formato es YYYYMMDD_HHMM_desc... quitamos los dos primeros
        if len(parts) >= 3 and len(parts[0]) == 8 and len(parts[1]) == 4:
            name = '_'.join(parts[2:])
    # Quitar prefijo web_ si existe (para archivos de scraper)
    if name.startswith('web_'):
        name = name[4:]
    # Ahora el nombre debería ser la categoría (posiblemente con guiones bajos)
    # Convertir guiones bajos a espacios y capitalizar cada palabra
    category = name.replace('_', ' ').strip()
    # Si está vacío, devolver "Desconocido"
    return category if category else "Desconocido"

def main():
    start = time.time()
    print("Iniciando indexación vectorial...")
    
    # Eliminar colección existente si existe
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        if COLLECTION_NAME in [c.name for c in client.list_collections()]:
            client.delete_collection(COLLECTION_NAME)
            print(f"Colección existente '{COLLECTION_NAME}' eliminada.")
    except Exception:
        pass
    
    # Crear nuevo cliente y colección
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    
    # Cargar modelo de embeddings
    print("Cargando modelo de embeddings...")
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Procesar archivos
    files_to_process = []
    for folder, source in [(DATOS_BOT_DIR, "maestro"), (DATOS_SCRAPER_DIR, "web")]:
        if not os.path.isdir(folder):
            print(f"Advertencia: carpeta {folder} no existe.")
            continue
        for fname in os.listdir(folder):
            if fname.endswith('.txt') and fname != EXCLUDE_FILE:
                files_to_process.append((folder, fname, source))
    
    total_files = len(files_to_process)
    total_chunks = 0
    
    for folder, fname, source in files_to_process:
        filepath = os.path.join(folder, fname)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # Eliminar líneas de cabecera que comienzan con '===' (como en los archivos de datos_bot)
            lines = content.split('\n')
            cleaned_lines = [ln for ln in lines if not ln.strip().startswith('===')]
            text = '\n'.join(cleaned_lines).strip()
            if not text:
                print(f"  {fname}: texto vacío después de limpiar cabecera, omitiendo.")
                continue
        except Exception as e:
            print(f"  Error leyendo {fname}: {e}")
            continue
        
        category = extract_category(fname)
        chunks = chunk_text(text, target_len=500)
        if not chunks:
            print(f"  {fname}: no se generaron fragmentos, omitiendo.")
            continue
        
        # Generar embeddings
        embeddings = embedder.encode(chunks, show_progress_bar=False)
        
        # Preparar datos para ChromaDB
        es_interno = any(x in fname.lower() for x in ["_interno", "_clases", "_tareas", "organigrama_interno", "_academia"])
        visibilidad = "interno" if es_interno else "publico"
        ids = [f"{fname}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "fuente": source,
                "archivo": fname,
                "categoria": category,
                "visibilidad": visibilidad
            }
            for _ in chunks
        ]
        
        # Añadir a la colección
        collection.add(
            embeddings=embeddings.tolist(),
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        total_chunks += len(chunks)
        print(f"  ✅ {fname}: {len(chunks)} fragmentos indexados (fuente: {source}, categoría: {category})")
    
    elapsed = time.time() - start
    print("\nIndexación completada.")
    print(f"Total de archivos procesados: {total_files}")
    print(f"Total de fragmentos indexados: {total_chunks}")
    print(f"Tiempo total: {elapsed:.2f} segundos")
    print(f"Colección guardada en: {CHROMA_PATH}")

if __name__ == "__main__":
    main()