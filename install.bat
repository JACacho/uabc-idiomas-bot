@echo off
echo Instalando UABCBot...
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
python setup_wizard.py
pause