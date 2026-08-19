"""بازسازی متنِ شکسته‌ی PDF با کمک مدل زبانی.

بسیاری از PDFهای فارسی، متن را تکه‌تکه و با ترتیب به‌هم‌ریخته بیرون می‌دهند
(مثلاً «س ی ستم» به‌جای «سیستم»). این ماژول هر صفحه را یک بار از مدل عبور
می‌دهد تا متن خوانا شود. نتیجه فقط یک‌بار هنگام ایندکس‌گذاری ساخته می‌شود.
"""

from __future__ import annotations

import asyncio
import re

from . import avalai, config, settings

REPAIR_SYSTEM = """تو یک ابزار بازسازی متن فارسی هستی.
متنی که می‌گیری از یک فایل PDF استخراج شده و به هم ریخته است: کلمه‌ها وسط راه شکسته‌اند،
حرف‌ها جدا افتاده‌اند، ترتیب بعضی عبارت‌ها جابه‌جا شده و ترکیب «لا» گاهی «ال» تایپ شده است.

کار تو فقط و فقط بازسازی است:
- کلمه‌های شکسته را به هم بچسبان و ترتیب طبیعی جمله‌ی فارسی را برگردان.
- املای درست را بنویس (سواالت ← سوالات، کاال ← کالا، اطالعات ← اطلاعات).
- عبارت‌های انگلیسی، نام جدول‌ها، دستورهای SQL، مسیر فایل‌ها، اعداد و کدهای خطا را عیناً و بدون تغییر نگه دار.
- ساختار سطرها، فهرست‌ها و جدول‌ها را تا حد ممکن حفظ کن.
- هیچ جمله‌ای اضافه نکن، هیچ چیزی را خلاصه یا حذف نکن، نظر نده.
- اگر بخشی واقعاً نامفهوم بود، همان را دست‌نخورده بگذار.

خروجی: فقط متن بازسازی‌شده. بدون مقدمه، بدون توضیح، بدون بلوک کد اضافه."""

MIN_CHARS = 60          # صفحه‌های خیلی کوتاه ارزش پردازش ندارند
MAX_CHARS = 6000        # سقف طول هر درخواست
CONCURRENCY = 4


# «و» تنها واژه‌ی تک‌حرفی رایج فارسی است و نشانه‌ی خرابی نیست
_REAL_SINGLES = {"و", "a", "i"}


def _needs_repair(text: str) -> bool:
    """اگر متن پر از تکه‌های تک‌حرفیِ بی‌معنا باشد یعنی استخراج خراب بوده."""
    words = [w for w in text.split() if w]
    if len(words) < 20:
        return False
    singles = sum(1 for w in words if len(w) == 1 and w not in _REAL_SINGLES and w.isalpha())
    return singles / len(words) > 0.03


async def repair_page(text: str, semaphore: asyncio.Semaphore) -> str:
    async with semaphore:
        try:
            result = await avalai.chat(
                [
                    {"role": "system", "content": REPAIR_SYSTEM},
                    {"role": "user", "content": text[:MAX_CHARS]},
                ],
                model=settings.fast_model(),
                temperature=0.0,
                max_tokens=4000,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[repair] صفحه بازسازی نشد → {avalai.describe(exc)}")
            return text
    result = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", result.strip())
    # اگر مدل متن را قیچی کرده باشد، به نسخه‌ی خام برمی‌گردیم
    if len(result) < len(text) * 0.5:
        return text
    return result


async def repair_pages(
    pages: list[str],
    *,
    on_progress=None,
    skip: set[int] | None = None,
) -> tuple[list[str], int]:
    """صفحه‌ها را بازسازی می‌کند و تعداد صفحه‌های بازسازی‌شده را برمی‌گرداند.

    صفحه‌هایی که در `skip` باشند دست‌نخورده می‌مانند — مثلاً صفحه‌هایی که
    قبلاً مدل بینایی خوانده و متنشان از قبل تمیز است.
    """
    if not settings.api_key():
        return pages, 0

    skip = skip or set()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    targets = [
        i for i, p in enumerate(pages)
        if i not in skip and len(p) >= MIN_CHARS and _needs_repair(p)
    ]
    if not targets:
        return pages, 0

    output = list(pages)
    done = 0

    async def run(index: int) -> None:
        nonlocal done
        output[index] = await repair_page(pages[index], semaphore)
        done += 1
        if on_progress:
            on_progress(done, len(targets))

    await asyncio.gather(*(run(i) for i in targets))
    return output, len(targets)
