#!/usr/bin/env python3
import re
import difflib

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def apply_fix1(content):
    # Fix 1a: replace fr_st list
    old_fr_st = '''fr_st = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplom", "traduction", "salut", "credit", "je ", "etud", "francais", "voud", "veux", "voaux", "quel", "quelle", "aime", "les ", "des ", "anglais"]'''
    new_fr_st = '''fr_st = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplom", "traduction", "salut", "credit", "je ", "etud", "francais", "voud", "veux", "voaux", "quel", "quelle", "aime", "les ", "des ", "anglais", "alors", "carriere", "carrière", "peux", "utilizar", "etudier", "trabajar", "quels", "quelles", "c'est", "sont", "dans", "por qué", "cómo", "cuál es", "me gustaría", "me gustaría", "estudio", "estudio", "vivo", "vivo", "ahí está", "ahi está", "por lo tanto", "también", "pero", "muy", "tres"]'''
    content = content.replace(old_fr_st, new_fr_st)
    
    # Fix 1b: replace the condition
    old_condition = '''    hf = sum(1 for w in fr_st if w in t)
    he = sum(1 for w in en_st if w in t)
    if hf >= 2 and hf > he:
        return "fr"
    if he >= 2 and he > hf:
        return "en"'''
    new_condition = '''    hf = sum(1 for w in fr_st if w in t)
    he = sum(1 for w in en_st if w in t)
    if hf >= 1 and hf >= he:
        return "fr"
    if he >= 2 and he > hf:
        return "en"'''
    content = content.replace(old_condition, new_condition)
    return content

def main():
    input_path = r"web_app.py"
    output_path = r"web_app_fix1.py"
    
    content = read_file(input_path)
    fixed = apply_fix1(content)
    write_file(output_path, fixed)
    
    # Show diff
    diff = difflib.unified_diff(
        content.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile='web_app.py',
        tofile='web_app_fix1.py',
        lineterm=''
    )
    print(''.join(diff))

if __name__ == '__main__':
    main()