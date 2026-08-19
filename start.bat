@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist venv (
  echo -^> ساخت محیط مجازی...
  python -m venv venv
)
call venv\Scripts\activate

echo -^> نصب وابستگی‌ها...
pip install -q --upgrade pip
pip install -q -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo فایل .env ساخته شد. کلید AvalAI را داخلش بگذارید و دوباره اجرا کنید.
  pause
  exit /b 1
)

python run.py
pause
