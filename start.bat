@echo off
REM ============================================================
REM  Support AI - Windows launcher
REM  Messages are in English on purpose: the Windows console
REM  often cannot render Persian text correctly.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   Support AI - starting up
echo ============================================================
echo.

REM ---------- 1. Python ----------
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python was not found.
  echo.
  echo     Install Python 3.10 or newer from python.org
  echo     IMPORTANT: tick "Add python.exe to PATH" during setup,
  echo     then close this window and run start.bat again.
  echo.
  pause
  exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [1/4] Python %PYVER% found.

REM ---------- 2. Virtual environment ----------
if not exist venv (
  echo [2/4] Creating virtual environment...
  python -m venv venv
  if errorlevel 1 (
    echo [X] Could not create the virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [2/4] Virtual environment already exists.
)
call venv\Scripts\activate.bat

REM ---------- 3. Dependencies ----------
echo [3/4] Installing dependencies ^(first run takes a few minutes^)...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [X] Installing dependencies failed. Check your internet connection.
  pause
  exit /b 1
)

REM ---------- 4. Config file ----------
if not exist .env (
  copy .env.example .env >nul
  echo [4/4] Created .env with default settings.
  echo       Default passwords: admin / support
  echo       Change them in .env before using this on a real server.
) else (
  echo [4/4] Using existing .env
)

echo.
echo   The admin panel will open in your browser.
echo   Put your AvalAI key in the "Key and models" tab.
echo   Press Ctrl+C in this window to stop the server.
echo.

set OPEN_BROWSER=true
python run.py

echo.
echo Server stopped.
pause
