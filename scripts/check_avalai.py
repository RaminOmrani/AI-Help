#!/usr/bin/env python3
"""بررسی سلامت اتصال به AvalAI.

اجرا:  python scripts/check_avalai.py
این اسکریپت کلید، اعتبار، فهرست مدل‌ها، پاسخ‌دهی و بردارسازی را تست می‌کند.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import avalai, config, vision  # noqa: E402

OK, BAD, INFO = "✅", "❌", "•"


# خانواده‌هایی که برای این کاربرد (پرسش‌وپاسخ فارسی روی مستندات) معنی دارند
_FAMILIES = [
    ("سریع و ارزان — گزینه‌ی مناسب CHAT_MODEL و FAST_MODEL",
     ("flash", "mini", "haiku", "lite", "nano")),
    ("قوی‌تر و گران‌تر — فقط اگر کیفیت پاسخ کافی نبود",
     ("pro", "opus", "sonnet", "gpt-5", "gpt-4o", "gpt-4.1")),
    ("بردارسازی — گزینه‌ی EMBEDDING_MODEL", ("embedding", "embed")),
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


def _sample_image() -> str:
    """یک تصویر کوچک با عدد ۱۲۳۴ می‌سازد تا خواندن تصویر تست شود."""
    import base64

    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=260, height=120)
    page.insert_text((40, 75), "1234", fontsize=54)
    png = page.get_pixmap(dpi=110).tobytes("png")
    doc.close()
    return "data:image/png;base64," + base64.b64encode(png).decode()


async def main() -> int:
    failures = 0
    print(f"\n{INFO} آدرس سرویس: {config.AVALAI_BASE_URL}")

    if not config.AVALAI_API_KEY:
        print(f"{BAD} کلید AVALAI_API_KEY تنظیم نشده است. فایل .env را بسازید.")
        return 1
    print(f"{OK} کلید تنظیم شده است ({config.AVALAI_API_KEY[:6]}…)")

    # ---------- اعتبار ----------
    try:
        credit = await avalai.credit()
        irt = credit.get("remaining_irt", 0)
        unit = credit.get("total_unit", credit.get("remaining_unit", 0))
        print(f"{OK} اعتبار: {irt:,.0f} تومان  |  {unit} واحد  |  نرخ: {credit.get('exchange_rate', '—')}")
        if float(unit or 0) <= 0 and float(irt or 0) <= 0:
            print(f"   ⚠️  اعتبار حساب صفر است؛ درخواست‌ها رد می‌شوند.")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"{BAD} خواندن اعتبار ناموفق: {exc}")

    # ---------- فهرست مدل‌ها ----------
    models: list[str] = []
    try:
        models = await avalai.list_models()
        print(f"{OK} {len(models)} مدل روی این حساب فعال است.")
        _print_candidates(models)
    except Exception as exc:  # noqa: BLE001
        print(f"{INFO} فهرست مدل‌ها در دسترس نبود: {exc}")

    for label, name in (
        ("مدل پاسخ‌دهی", config.CHAT_MODEL),
        ("مدل سبک", config.FAST_MODEL),
        ("مدل بینایی", config.VISION_MODEL),
        ("مدل بردارسازی", config.EMBEDDING_MODEL),
    ):
        if models and name not in models:
            print(f"   ⚠️  {label} «{name}» در فهرست حساب شما نیست.")
            similar = [m for m in models if name.split("-")[0] in m][:5]
            if similar:
                print(f"      گزینه‌های نزدیک: {', '.join(similar)}")

    # ---------- تست پاسخ‌دهی ----------
    try:
        answer = await avalai.chat(
            [{"role": "user", "content": "فقط بنویس: سلام"}],
            model=config.CHAT_MODEL,
            max_tokens=20,
        )
        print(f"{OK} مدل پاسخ‌دهی «{config.CHAT_MODEL}» کار می‌کند → {answer[:40]}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"{BAD} مدل پاسخ‌دهی «{config.CHAT_MODEL}» کار نکرد: {exc}")

    # ---------- تست بینایی ----------
    if config.VISION_ENABLED:
        try:
            data_url = _sample_image()
            answer = await avalai.chat(
                [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": "فقط عددی که در تصویر نوشته شده را بنویس."},
                    ],
                }],
                model=config.VISION_MODEL,
                max_tokens=30,
            )
            if "1234" in answer.replace("۱۲۳۴", "1234"):
                print(f"{OK} مدل بینایی «{config.VISION_MODEL}» تصویر را درست خواند.")
            else:
                failures += 1
                print(f"{BAD} مدل بینایی تصویر را درست نخواند (پاسخ: {answer[:60]}).")
                print("   یعنی اسکرین‌شات‌های داخل PDF خوانده نمی‌شوند. VISION_MODEL را عوض کنید.")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"{BAD} مدل بینایی «{config.VISION_MODEL}» کار نکرد: {exc}")
            print("   یک مدل با پشتیبانی تصویر انتخاب کنید (Gemini، GPT-5.x، Claude).")

    # ---------- تست بردارسازی ----------
    try:
        vectors = await avalai.embed(["تست جستجوی معنایی"])
        print(f"{OK} مدل بردارسازی «{config.EMBEDDING_MODEL}» کار می‌کند (بُعد {len(vectors[0])})")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"{BAD} مدل بردارسازی «{config.EMBEDDING_MODEL}» کار نکرد: {exc}")
        print("   بدون بردارسازی، سیستم به جستجوی کلیدواژه‌ای برمی‌گردد (کیفیت پایین‌تر).")

    print()
    if failures:
        print(f"{BAD} {failures} مورد ناموفق بود — .env را اصلاح کنید.\n")
    else:
        print(f"{OK} همه چیز آماده است. سرور را اجرا کنید: python run.py\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
