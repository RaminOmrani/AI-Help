# ============================================================
#  اجرای پروژه داخل داکر — اگر نمی‌خواهید روی سرور پایتون نصب کنید
#
#    docker compose -f deploy/docker-compose.yml up -d
# ============================================================
FROM python:3.12-slim

# PyMuPDF برای رندر صفحه‌ها به این کتابخانه‌ها نیاز دارد
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY web/ ./web/
COPY scripts/ ./scripts/
COPY run.py .

# دیتابیس و فایل‌های بارگذاری‌شده بیرون از ایمیج نگه داشته می‌شوند
VOLUME ["/app/data", "/app/docs"]

ENV HOST=0.0.0.0 PORT=8000 TRUST_PROXY=true
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
