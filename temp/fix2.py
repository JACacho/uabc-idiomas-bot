#!/usr/bin/env python3
import re
import difflib

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def apply_fix2(content):
    # Fix 2A: _tiene_fecha_pasada
    old_tiene_fecha = '''    # Fechas tipo "18 de agosto" (asume año actual)
    for d, m in re.findall(r'(\\d{1,2})\\s+de\\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)', texto.lower()):
        try:
            if _date(hoy.year, meses[m], int(d)) < hoy:
                return True
        except Exception:
            pass'''
    new_tiene_fecha = '''    # Fechas tipo "18 de agosto" (asume año actual)
    # NO bloquear si es hoy, mañana o ayer (margen de 1 día)
    ayer = hoy - timedelta(days=1)
    for d, m in re.findall(r'(\\d{1,2})\\s+de\\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)', texto.lower()):
        try:
            fecha_texto = _date(hoy.year, meses[m], int(d))
            if fecha_texto < ayer:
                return True
        except Exception:
            pass'''
    content = content.replace(old_tiene_fecha, new_tiene_fecha)
    
    # Fix 2B: cargar_contexto - add boost for recent fragments
    old_cargar_contexto = '''            fragmentos = results.get("documents", [[]])[0]
            fragmentos = [f for f in fragmentos if not _tiene_fecha_pasada(f)]
            partes.extend(fragmentos)'''
    new_cargar_contexto = '''            fragmentos = results.get("documents", [[]])[0]
            fragmentos = [f for f in fragmentos if not _tiene_fecha_pasada(f)]
            # Si la pregunta menciona "hoy", "mañana" o "esta semana", añadir avisos recientes al inicio
            pregunta_lower = (pregunta or "").lower()
            if any(k in pregunta_lower for k in ["hoy", "mañana", "manana", "esta semana", "proxim"]):
                try:
                    todos = collection.get(include=["documents", "metadatas"])
                    recientes = []
                    for doc, meta in zip(todos.get("documents", []), todos.get("metadatas", [])):
                        archivo = meta.get("archivo", "")
                        if "20261006" in archivo or "20261007" in archivo:
                            recientes.append(doc)
                if recientes:
                    fragmentos = recientes[:3] + fragmentos
                except Exception:
                    pass
            partes.extend(fragmentos)'''
    content = content.replace(old_cargar_contexto, new_cargar_contexto)
    
    # Fix 2C: sistema_prompt
    old_sistema_prompt = '''        "FECHAS Y EVENTOS: si preguntan por 'hoy', 'mañana', 'esta semana', 'la próxima semana' o 'pronto', menciona PRIMERO los eventos y avisos con fecha dentro de los próximos 14 días a partir de hoy (con fecha, hora y lugar si los tienes); NUNCA cites fechas que ya pasaron ni te contradigas. '''
    new_sistema_prompt = '''        "FECHAS Y EVENTOS: si preguntan por 'hoy', 'mañana' o 'esta semana', SIEMPRE revisa si hay avisos que mencionen esas fechas específicas o un rango que las incluya. Si encuentras un aviso de suspensión o cambio de modalidad vigente para HOY o MAÑANA, DEBES informarlo claramente al usuario como PRIMERA respuesta. NUNCA digas 'no hay información' si existe un aviso vigente que cubra esas fechas. '''
    content = content.replace(old_sistema_prompt, new_sistema_prompt)
    return content

def main():
    input_path = r"web_app_fix1.py"
    output_path = r"web_app_fix2.py"
    
    content = read_file(input_path)
    fixed = apply_fix2(content)
    write_file(output_path, fixed)
    
    # Show diff
    diff = difflib.unified_diff(
        content.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile='web_app_fix1.py',
        tofile='web_app_fix2.py',
        lineterm=''
    )
    print(''.join(diff))

if __name__ == '__main__':
    main()