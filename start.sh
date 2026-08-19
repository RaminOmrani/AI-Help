#!/usr/bin/env bash
# راه‌اندازی سریع روی لینوکس / مک
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  echo "→ ساخت محیط مجازی…"
  python3 -m venv venv
fi
source venv/bin/activate

echo "→ نصب وابستگی‌ها…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  فایل .env ساخته شد — کلید AvalAI را داخلش بگذارید و دوباره اجرا کنید."
  exit 1
fi

python run.py
