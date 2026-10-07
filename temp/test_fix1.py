import re
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

with open('web_app.py', 'r') as f:
    content = f.read()
print('Length of content:', len(content))
print('First 500 chars:', content[:500])
fixed = apply_fix1(content)
print('Length of fixed:', len(fixed))
if fixed == content:
    print('No change')
else:
    print('Change')
    # Find the first difference
    for i, (c1, c2) in enumerate(zip(content, fixed)):
        if c1 != c2:
            print(f'First difference at position {i}: {repr(content[i])} vs {repr(fixed[i])}')
            break