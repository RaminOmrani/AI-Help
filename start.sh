#!/usr/bin/env bash
# راه‌اندازی سریع روی لینوکس و مک
set -e
cd "$(dirname "$0")"

echo
echo "════════════════════════════════════════════════════════"
echo "  دستیار پشتیبانی هوشمند — راه‌اندازی"
echo "════════════════════════════════════════════════════════"
echo

# ---------- ۱. پایتون ----------
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ پایتون ۳ پیدا نشد. اول آن را نصب کنید."
  exit 1
fi
echo "[۱/۴] $(python3 --version)"

# ---------- ۲. محیط مجازی ----------
if [ ! -d venv ]; then
  echo "[۲/۴] ساخت محیط مجازی…"
  python3 -m venv venv
else
  echo "[۲/۴] محیط مجازی از قبل وجود دارد."
fi
# shellcheck disable=SC1091
source venv/bin/activate

# ---------- ۳. وابستگی‌ها ----------
echo "[۳/۴] نصب وابستگی‌ها (بار اول چند دقیقه طول می‌کشد)…"
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

# ---------- ۴. فایل تنظیمات ----------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[۴/۴] فایل .env با مقادیر پیش‌فرض ساخته شد."
  echo "      رمزهای پیش‌فرض: admin / support — قبل از استفاده‌ی واقعی عوضشان کنید."
else
  echo "[۴/۴] از فایل .env موجود استفاده می‌شود."
fi

echo
echo "کلید AvalAI را در پنل مدیریت ← تب «کلید و مدل‌ها» وارد کنید."
echo "برای توقف سرور: Ctrl+C"

export OPEN_BROWSER=true
python run.py
