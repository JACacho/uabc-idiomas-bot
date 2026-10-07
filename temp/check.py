with open('web_app.py', 'r') as f:
    content = f.read()
old_fr_st = '''fr_st = ["bonjour", "merci", "combien", "pour", "avec", "vous", "diplom", "traduction", "salut", "credit", "je ", "etud", "francais", "voud", "veux", "voaux", "quel", "quelle", "aime", "les ", "des ", "anglais"]'''
if old_fr_st in content:
    print('Found old fr_st')
else:
    print('Old fr_st not found')
    # Let's see what is there
    import re
    match = re.search(r'fr_st = \[.*\]', content)
    if match:
        print('Found:', match.group())