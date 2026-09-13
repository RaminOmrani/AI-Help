#!/usr/bin/env python3
"""تغییر رمز ورود مدیر و کارشناس پشتیبانی، با رمز دلخواه خودتان.

    python3 scripts/setpass.py              # پرسش‌وپاسخ (رمز هنگام تایپ دیده نمی‌شود)
    python3 scripts/setpass.py --show       # همان، ولی رمز هنگام تایپ دیده می‌شود
    python3 scripts/setpass.py --admin 'رمز-من'          # بدون پرسش
    python3 scripts/setpass.py --admin 'a' --agent 'b'   # هر دو با هم

این اسکریپت به هیچ کتابخانه‌ای نیاز ندارد و مستقیم با python3 اجرا می‌شود.
فقط دو خط ADMIN_PASSWORD و AGENT_PASSWORD را در .env عوض می‌کند و به بقیه‌ی
تنظیمات دست نمی‌زند. نسخه‌ی قبلی در .env.backup نگه داشته می‌شود.
"""

from __future__ import annotations

import argparse
import getpass
import re
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

MIN_LENGTH = 8

# این دو رشته در فایل .env معنای خاص دارند و نمی‌شود داخل رمز گذاشتشان:
#   '   پایان مقدار را اعلام می‌کند
#   ${  به‌جای متن، مقدار یک متغیر دیگر خوانده می‌شود
FORBIDDEN = {"'": "علامت آپاستروف ( ' )", "${": "دنباله‌ی ${"}


def reject_reason(value: str) -> str | None:
    """اگر رمز قابل قبول نیست، دلیلش را برمی‌گرداند؛ وگرنه None."""
    if len(value) < MIN_LENGTH:
        return f"رمز باید حداقل {MIN_LENGTH} نویسه باشد (الان {len(value)} نویسه است)."
    if value != value.strip():
        return "رمز نباید با فاصله شروع یا تمام شود (فاصله‌ی اول و آخر خوانده نمی‌شود)."
    if "\n" in value or "\r" in value:
        return "رمز نباید چند خطی باشد."
    for bad, label in FORBIDDEN.items():
        if bad in value:
            return f"{label} در رمز قابل استفاده نیست. یک نویسه‌ی دیگر بگذارید."
    return None


def set_env_value(text: str, key: str, value: str) -> str:
    """مقدار یک کلید را در متن .env جایگزین یا اضافه می‌کند.

    مقدار همیشه داخل آپاستروف نوشته می‌شود تا نویسه‌هایی مثل # یا فاصله
    یا & دست‌نخورده باقی بمانند.
    """
    line = f"{key}='{value}'"
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda _: line, text)
    return text.rstrip("\n") + f"\n{line}\n"


def ask(label: str, show: bool) -> str | None:
    """رمز را دو بار می‌پرسد تا اشتباه تایپی رد شود. برای انصراف: خالی بگذارید."""
    reader = input if show else getpass.getpass
    while True:
        first = reader(f"  {label} (خالی = بی‌خیال): ")
        if not first:
            return None
        problem = reject_reason(first)
        if problem:
            print(f"  ✗ {problem}\n")
            continue
        second = reader("  یک بار دیگر برای اطمینان: ")
        if first != second:
            print("  ✗ دو بار یکسان نبود. دوباره تلاش کنید.\n")
            continue
        return first


def main() -> int:
    parser = argparse.ArgumentParser(description="تغییر رمز مدیر و کارشناس پشتیبانی")
    parser.add_argument("--admin", help="رمز جدید ورود به /admin")
    parser.add_argument("--agent", help="رمز جدید ورود به /agent")
    parser.add_argument("--show", action="store_true",
                        help="رمز هنگام تایپ روی صفحه دیده شود")
    args = parser.parse_args()

    if not ENV_PATH.exists():
        print(f"✗ فایل {ENV_PATH} پیدا نشد. اول preflight را اجرا کنید.")
        return 1

    new: dict[str, str] = {}

    if args.admin or args.agent:
        for key, value in (("ADMIN_PASSWORD", args.admin), ("AGENT_PASSWORD", args.agent)):
            if value is None:
                continue
            problem = reject_reason(value)
            if problem:
                print(f"✗ {key}: {problem}")
                return 1
            new[key] = value
    else:
        print("\n  رمز دلخواه خودتان را بگذارید. حروف فارسی هم قبول است.")
        if not args.show:
            print("  هنگام تایپ چیزی روی صفحه نمی‌بینید — طبیعی است.")
        print()
        admin = ask("رمز مدیر (صفحه‌ی /admin)", args.show)
        if admin:
            new["ADMIN_PASSWORD"] = admin
        agent = ask("رمز کارشناس پشتیبانی (صفحه‌ی /agent)", args.show)
        if agent:
            new["AGENT_PASSWORD"] = agent

    if not new:
        print("\n  چیزی عوض نشد.\n")
        return 0

    backup = ENV_PATH.parent / ".env.backup"
    shutil.copy(ENV_PATH, backup)

    text = ENV_PATH.read_text(encoding="utf-8")
    for key, value in new.items():
        text = set_env_value(text, key, value)
    ENV_PATH.write_text(text, encoding="utf-8")

    print(f"\n✅ عوض شد: {'، '.join(new)}   (نسخه‌ی قبلی: {backup.name})")
    print("\n  تا سرویس ری‌استارت نشود، رمز قبلی کار می‌کند. این را بزنید:")
    print("     sudo systemctl restart aiassist\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
