@echo off
cd /d "E:\Programming\CoreFrame"
if not exist "venv" (
    echo [*] Creando entorno virtual...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo [*] Iniciando CoreFrame...
python app.py
pause