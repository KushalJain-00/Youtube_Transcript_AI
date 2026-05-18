@echo off
echo ========================================
echo   YT.AI — YouTube Intelligence Platform
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.9+ from python.org
    pause
    exit /b 1
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt -q

echo.
echo Starting server on http://localhost:5000
echo Press Ctrl+C to stop.
echo.
start "" http://localhost:5000

python app.py
pause
