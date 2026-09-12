#!/usr/bin/env python3
"""بررسی آمادگی برای انتشار روی اینترنت.

    python scripts/preflight.py            # فقط بررسی
    python scripts/preflight.py --fix      # رمزها و کلید امن بساز و در .env بنویس

قبل از باز کردن سایت روی دامنه‌ی عمومی این را اجرا کنید.
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db, security, settings  # noqa: E402

OK, BAD, INFO = "✅", "❌", "•"
ENV_PATH = config.BASE_DIR / ".env"


def strong_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def set_env_value(text: str, key: str, value: str) -> str:
    """مقدار یک کلید را در متن .env جایگزین یا اضافه می‌کند."""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip("\n") + f"\n{line}\n"


def fix_env(domain: str | None) -> None:
    if not ENV_PATH.exists():
        example = config.BASE_DIR / ".env.example"
        if not example.exists():
            print(f"{BAD} نه .env هست نه .env.example — پروژه ناقص است.")
            raise SystemExit(1)
        shutil.copy(example, ENV_PATH)
        print(f"{INFO} .env از روی نمونه ساخته شد.")

    backup = ENV_PATH.parent / ".env.backup"
    shutil.copy(ENV_PATH, backup)

    text = ENV_PATH.read_text(encoding="utf-8")
    generated: dict[str, str] = {}

    for key, current in (
        ("ADMIN_PASSWORD", config.ADMIN_PASSWORD),
        ("AGENT_PASSWORD", config.AGENT_PASSWORD),
    ):
        if (current in security.INSECURE_DEFAULTS.values()
                or security.is_placeholder(current)
                or len(current) < 12):
            generated[key] = strong_password()

    if (config.SECRET_KEY == security.INSECURE_DEFAULTS["SECRET_KEY"]
            or security.is_placeholder(config.SECRET_KEY)
            or len(config.SECRET_KEY) < 32):
        generated["SECRET_KEY"] = secrets.token_urlsafe(48)

    for key, value in generated.items():
        text = set_env_value(text, key, value)

    text = set_env_value(text, "TRUST_PROXY", "true")
    text = set_env_value(text, "HOST", "127.0.0.1")
    if domain:
        text = set_env_value(text, "ALLOWED_ORIGINS", f"https://{domain}")

    ENV_PATH.write_text(text, encoding="utf-8")

    print(f"\n{OK} فایل .env به‌روز شد (نسخه‌ی قبلی: {backup.name})\n")
    if generated:
        print("  ── این مقادیر ساخته شدند. همین حالا جایی امن ذخیره‌شان کنید:")
        for key, value in generated.items():
            shown = value if key != "SECRET_KEY" else f"{value[:8]}… (در .env ذخیره شد)"
            print(f"     {key} = {shown}")
        print()
    print("  ── تنظیم شد:")
    print("     HOST=127.0.0.1        سرور فقط از روی خودِ ماشین شنیده می‌شود (nginx جلویش است)")
    print("     TRUST_PROXY=true      آی‌پی واقعی کاربر از هدر nginx خوانده شود")
    if domain:
        print(f"     ALLOWED_ORIGINS=https://{domain}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="بررسی آمادگی انتشار")
    parser.add_argument("--fix", action="store_true", help="رمز و کلید امن بساز و در .env بنویس")
    parser.add_argument("--domain", help="دامنه‌ی نهایی، مثلاً aiassist.softmiliac.com")
    args = parser.parse_args()

    if args.fix:
        fix_env(args.domain)
        print(f"{INFO} حالا سرور را ری‌استارت کنید و دوباره این اسکریپت را بزنید.\n")
        return 0

    db.init_db()
    print("\n" + "═" * 58)
    print("  بررسی آمادگی برای انتشار عمومی")
    print("═" * 58 + "\n")

    issues = security.security_issues()
    for issue in issues:
        print(f"{BAD} {issue['text']}")

    checks: list[tuple[bool, str, str]] = [
        (bool(settings.api_key()), "کلید AvalAI ثبت شده است",
         "کلید ثبت نشده — بدون آن هیچ پاسخی داده نمی‌شود."),
        (config.HOST == "127.0.0.1", "سرور فقط روی لوکال گوش می‌دهد (پشت nginx)",
         f"HOST={config.HOST} — اگر nginx جلویش است، 127.0.0.1 امن‌تر است."),
        (config.TRUST_PROXY, "TRUST_PROXY روشن است (آی‌پی واقعی کاربر خوانده می‌شود)",
         "TRUST_PROXY خاموش است — پشت nginx همه‌ی کاربران یک آی‌پی دیده می‌شوند "
         "و محدودیت نرخ درست کار نمی‌کند."),
    ]

    warnings = 0
    for ok, good, bad in checks:
        if ok:
            print(f"{OK} {good}")
        else:
            warnings += 1
            print(f"{BAD} {bad}")

    from app import rag
    index = rag.stats()
    if index["ready"]:
        print(f"{OK} {index['ready']} سند ایندکس شده ({index['chunks']} تکه)")
    else:
        warnings += 1
        print(f"{BAD} هیچ سندی ایندکس نشده — دستیار چیزی برای پاسخ دادن ندارد.")

    print(f"\n{INFO} محدودیت نرخ: "
          f"{config.RATE_LIMIT_PER_MINUTE} سوال در دقیقه، "
          f"{config.RATE_LIMIT_PER_DAY} سوال در روز برای هر آی‌پی")

    total = len(issues) + warnings
    print()
    if total:
        print(f"{BAD} {total} مورد باید حل شود.")
        print("   برای ساخت خودکار رمز و کلید امن:")
        print("   python scripts/preflight.py --fix --domain aiassist.softmiliac.com\n")
        return 1

    print(f"{OK} آماده‌ی انتشار است.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
