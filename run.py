#!/usr/bin/env python3
"""اجرای سرور دستیار پشتیبانی.

    python run.py

سپس در مرورگر:
    http://localhost:8000/        صفحه‌ی مشتری
    http://localhost:8000/agent   کنسول پشتیبان
    http://localhost:8000/admin   پنل مدیریت
"""

import uvicorn

from app import config

if __name__ == "__main__":
    print("\n" + "═" * 58)
    print("  دستیار پشتیبانی هوشمند")
    print("═" * 58)
    print(f"  صفحه‌ی مشتری : http://localhost:{config.PORT}/")
    print(f"  کنسول پشتیبان: http://localhost:{config.PORT}/agent")
    print(f"  پنل مدیریت   : http://localhost:{config.PORT}/admin")
    print(f"  مدل          : {config.CHAT_MODEL}")
    if not config.AVALAI_API_KEY:
        print("  ⚠️  کلید AVALAI_API_KEY تنظیم نشده — فایل .env را بسازید.")
    print("═" * 58 + "\n")

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
