#!/usr/bin/env python3
import sys

def main():
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # Find the line to replace
    for i, line in enumerate(lines):
        if line.strip() == 'if lang_pref not in ("es", "en", "fr"):':
            # The next line should be the indented line: '                        lang = "es"'
            # We'll replace that next line.
            if i+1 < len(lines) and lines[i+1].strip() == 'lang = "es"':
                lines[i+1] = '                        lang = lang_detect\n'
                break
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

if __name__ == '__main__':
    main()