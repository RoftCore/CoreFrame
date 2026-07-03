@echo off
cd /d "%~dp0"
if not exist "venv" (
    echo [*] Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo [*] Starting CoreFrame...
python app.py
pause