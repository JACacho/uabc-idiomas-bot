#!/usr/bin/env python3
import re
import difflib

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def apply_fix3(content):
    # Fix 3: visibility filter in cargar_contexto
    old_where = '''            where_filter = {"visibilidad": {"$in": ["publico", "interno"]}} if rol == "interno" else {"visibilidad": "publico"}'''
    new_where = '''            where_filter = {"visibilidad": {"$in": ["publico", "interno"]}} if rol == "interno" else {"visibilidad": {"$in": ["publico"]}}'''
    content = content.replace(old_where, new_where)
    return content

def main():
    input_path = r"web_app_fix2_fixed.py"
    output_path = r"web_app_fix3.py"
    
    content = read_file(input_path)
    fixed = apply_fix3(content)
    write_file(output_path, fixed)
    
    # Show diff
    diff = difflib.unified_diff(
        content.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile='web_app_fix2_fixed.py',
        tofile='web_app_fix3.py',
        lineterm=''
    )
    print(''.join(diff))

if __name__ == '__main__':
    main()