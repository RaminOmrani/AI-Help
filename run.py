#!/usr/bin/env python3
"""اجرای سرور دستیار پشتیبانی.

    python run.py

سپس در مرورگر:
    http://localhost:8000/        صفحه‌ی مشتری
    http://localhost:8000/agent   کنسول پشتیبان
    http://localhost:8000/admin   پنل مدیریت
"""

import threading
import webbrowser

import uvicorn

from app import config, db, security, settings

if __name__ == "__main__":
    db.init_db()

    print("\n" + "═" * 58)
    print("  دستیار پشتیبانی هوشمند")
    print("═" * 58)
    print(f"  صفحه‌ی مشتری : http://localhost:{config.PORT}/")
    print(f"  کنسول پشتیبان: http://localhost:{config.PORT}/agent")
    print(f"  پنل مدیریت   : http://localhost:{config.PORT}/admin")
    print(f"  مدل          : {settings.chat_model()}")
    if not settings.api_key():
        print("  ⚠️  کلید AvalAI ثبت نشده — در پنل مدیریت، تب «کلید و مدل‌ها» واردش کنید.")
    security.print_startup_warnings()
    print("═" * 58 + "\n")

    if config.OPEN_BROWSER:
        url = f"http://localhost:{config.PORT}/admin"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
