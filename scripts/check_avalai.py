#!/usr/bin/env python3
"""بررسی سلامت اتصال به AvalAI.

    python scripts/check_avalai.py

کلید، اعتبار، مدل‌های فعال حساب، پاسخ‌دهی، خواندن تصویر و بردارسازی را تست می‌کند.
همین تست‌ها از پنل مدیریت ← «کلید و مدل‌ها» ← «تست اتصال» هم قابل اجرا هستند.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import avalai, config, db, diagnostics, settings  # noqa: E402

OK, BAD, INFO = "✅", "❌", "•"

# خانواده‌هایی که برای این کاربرد (پرسش‌وپاسخ فارسی روی مستندات) معنی دارند
_FAMILIES = [
    ("سریع و ارزان — گزینه‌ی مناسب مدل پاسخ‌دهی و مدل سبک",
     ("flash", "mini", "haiku", "lite", "nano")),
    ("قوی‌تر و گران‌تر — فقط اگر کیفیت پاسخ کافی نبود",
     ("pro", "opus", "sonnet", "gpt-5", "gpt-4.1")),
    ("بردارسازی — گزینه‌ی مدل بردارسازی", ("embedding", "embed")),
]


def _print_candidates(models: list[str]) -> None:
    """مدل‌های حساب را دسته‌بندی می‌کند تا انتخاب راحت‌تر باشد."""
    for title, keywords in _FAMILIES:
        matches = sorted({m for m in models if any(k in m.lower() for k in keywords)})
        if not matches:
            continue
        print(f"\n   ── {title}")
        for name in matches[:18]:
            print(f"      {name}")
        if len(matches) > 18:
            print(f"      … و {len(matches) - 18} مورد دیگر")
    print()


async def main() -> int:
    db.init_db()
    print(f"\n{INFO} آدرس سرویس: {config.AVALAI_BASE_URL}")

    results = await diagnostics.run_checks()
    failures = 0

    for check in results:
        mark = OK if check["ok"] else BAD
        print(f"{mark} {check['name']}" + (f" — {check['detail']}" if check["detail"] else ""))
        if check["hint"]:
            print(f"   ↳ {check['hint']}")
        if not check["ok"]:
            failures += 1

    # فهرست مدل‌های فعال حساب
    if settings.api_key():
        try:
            models = await avalai.list_models()
            print(f"\n{OK} {len(models)} مدل روی این حساب فعال است.")
            _print_candidates(models)
            for label, name in (
                ("مدل پاسخ‌دهی", settings.chat_model()),
                ("مدل سبک", settings.fast_model()),
                ("مدل بینایی", settings.vision_model()),
                ("مدل بردارسازی", settings.embedding_model()),
            ):
                if name not in models:
                    print(f"   ⚠️  {label} «{name}» در فهرست حساب شما نیست.")
                    similar = [m for m in models if name.split("-")[0] in m][:5]
                    if similar:
                        print(f"      گزینه‌های نزدیک: {', '.join(similar)}")
        except Exception as exc:  # noqa: BLE001
            print(f"{INFO} فهرست مدل‌ها در دسترس نبود: {exc}")

    print()
    if failures:
        print(f"{BAD} {failures} مورد ناموفق بود — تنظیمات را از پنل مدیریت یا فایل .env اصلاح کنید.\n")
    else:
        print(f"{OK} همه چیز آماده است. سرور را اجرا کنید: python run.py\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
