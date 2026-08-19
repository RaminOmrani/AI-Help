"""خواندن صفحه‌های تصویری PDF با مدل بینایی.

بخش بزرگی از راهنماهای نرم‌افزاری، اسکرین‌شات است: پنجره‌ی نصب، مسیر منو،
نام فیلدها و دکمه‌ها. استخراج متنیِ معمولی این‌ها را اصلاً نمی‌بیند.

این ماژول صفحه‌های عکس‌دار را به تصویر رندر می‌کند و به یک مدل بینایی می‌دهد
تا هم متن صفحه را تمیز بازنویسی کند و هم محتوای اسکرین‌شات‌ها را به متنِ
قابل جستجو تبدیل کند. یک‌بار هنگام ایندکس‌گذاری اجرا می‌شود، نه در هر سوال.
"""

from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path

from . import avalai, config

VISION_SYSTEM = """تو یک ابزار تبدیل صفحه‌ی راهنمای نرم‌افزار به متن هستی.
تصویر یک صفحه از راهنمای فارسیِ یک نرم‌افزار حسابداری/فروشگاهی را می‌بینی؛
متن استخراج‌شده‌ی همان صفحه هم (که معمولاً شکسته و به‌هم‌ریخته است) در اختیارت است.

خروجی تو باید بازنویسی کاملِ همان صفحه باشد، شامل:

۱. **متن صفحه** — دقیق، با املای درست فارسی و ترتیب طبیعی جمله‌ها.
   کلمه‌های شکسته را به هم بچسبان («س ی ستم» ← «سیستم»، «سواالت» ← «سوالات»).

۲. **محتوای هر اسکرین‌شات** — برای هر تصویر، زیر عنوان «تصویر: …» بنویس:
   - عنوان پنجره یا فرم (عیناً، حتی اگر انگلیسی است)
   - مسیر منو یا مسیر فایل اگر دیده می‌شود
   - نام فیلدها و مقدارشان
   - نام دکمه‌ها، به‌ویژه دکمه‌ای که باید زده شود (Next، OK، ذخیره، …)
   - پیام خطا یا متن هشدار، عیناً
   - اگر جایی با کادر رنگی یا فلش مشخص شده، بگو چه چیزی مشخص شده است

قواعد سخت:
- فقط چیزی را بنویس که در تصویر می‌بینی. حدس نزن، تفسیر نکن، مرحله اضافه نکن.
- نام‌های انگلیسی، دستورهای SQL، مسیر فایل، اعداد و کد خطا را عیناً بنویس.
- اگر صفحه اسکرین‌شات نداشت، فقط متن صفحه را تمیز بنویس.
- بدون مقدمه، بدون نتیجه‌گیری، بدون توضیح درباره‌ی کاری که کردی."""

MIN_IMAGE_PIXELS = 150 * 150  # کوچک‌تر از این معمولاً لوگو یا آیکون است


def pages_with_images(pdf_path: Path) -> list[int]:
    """شماره‌ی صفحه‌هایی (از صفر) که اسکرین‌شات قابل‌توجه دارند."""
    import pymupdf

    targets: list[int] = []
    with pymupdf.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            for image in page.get_images(full=True):
                try:
                    if image[2] * image[3] >= MIN_IMAGE_PIXELS:
                        targets.append(index)
                        break
                except (IndexError, TypeError):
                    continue
    return targets


def _content_clip(page) -> object | None:
    """کادر محتوای صفحه — حاشیه‌ی سفید بی‌فایده حذف می‌شود تا تصویر سبک‌تر شود."""
    import pymupdf

    boxes = [pymupdf.Rect(b[:4]) for b in page.get_text("blocks")]
    for block in page.get_image_info():
        boxes.append(pymupdf.Rect(block["bbox"]))

    content = pymupdf.Rect()
    for box in boxes:
        if not box.is_empty and not box.is_infinite:
            content |= box
    if content.is_empty or content.is_infinite:
        return None

    content += (-14, -14, 14, 14)  # کمی حاشیه
    content &= page.rect
    # اگر برش تقریباً کل صفحه است یا مشکوک کوچک است، بی‌خیالش
    area_ratio = content.get_area() / max(page.rect.get_area(), 1)
    if area_ratio > 0.92 or area_ratio < 0.12:
        return None
    return content


def render_page(pdf_path: Path, index: int, dpi: int) -> bytes:
    """یک صفحه را به JPEG تبدیل می‌کند (سبک‌تر از PNG و برای اسکرین‌شات کافی)."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        page = doc[index]
        clip = _content_clip(page)
        pixmap = page.get_pixmap(dpi=dpi, clip=clip)
        return pixmap.tobytes("jpeg", jpg_quality=config.VISION_JPEG_QUALITY)


async def _read_page(
    pdf_path: Path,
    index: int,
    raw_text: str,
    semaphore: asyncio.Semaphore,
) -> str:
    async with semaphore:
        try:
            jpeg = await asyncio.to_thread(render_page, pdf_path, index, config.VISION_DPI)
            data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
            result = await avalai.chat(
                [
                    {"role": "system", "content": VISION_SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {
                                "type": "text",
                                "text": (
                                    f"صفحه‌ی {index + 1}.\n\n"
                                    f"متن خام استخراج‌شده (ممکن است شکسته باشد):\n{raw_text[:4000]}"
                                ),
                            },
                        ],
                    },
                ],
                model=config.VISION_MODEL,
                temperature=0.0,
                max_tokens=4000,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[vision] صفحه‌ی {index + 1} خوانده نشد: {exc}")
            return raw_text

    result = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", result.strip())
    # اگر مدل خروجی بی‌ربط یا خیلی کوتاه داد، به متن خام برمی‌گردیم
    if len(result) < 40:
        return raw_text
    return result


async def read_pages(
    pdf_path: Path,
    pages: list[str],
    *,
    on_progress=None,
) -> tuple[list[str], list[int]]:
    """صفحه‌های عکس‌دار را با مدل بینایی می‌خواند.

    خروجی: (صفحه‌های به‌روزشده، شماره‌ی صفحه‌هایی که با تصویر خوانده شدند)
    """
    if not config.AVALAI_API_KEY or not config.VISION_ENABLED:
        return pages, []

    targets = await asyncio.to_thread(pages_with_images, pdf_path)
    targets = [i for i in targets if i < len(pages)]
    if not targets:
        return pages, []

    capped = False
    if len(targets) > config.VISION_MAX_PAGES:
        print(
            f"[vision] {len(targets)} صفحه‌ی عکس‌دار پیدا شد؛ "
            f"فقط {config.VISION_MAX_PAGES} صفحه‌ی اول خوانده می‌شود "
            f"(سقف VISION_MAX_PAGES)."
        )
        targets = targets[: config.VISION_MAX_PAGES]
        capped = True

    semaphore = asyncio.Semaphore(config.VISION_CONCURRENCY)
    output = list(pages)
    done = 0

    async def run(index: int) -> None:
        nonlocal done
        output[index] = await _read_page(pdf_path, index, pages[index], semaphore)
        done += 1
        if on_progress:
            on_progress(done, len(targets))

    await asyncio.gather(*(run(i) for i in targets))
    if capped:
        print(f"[vision] {len(targets)} صفحه خوانده شد؛ بقیه فقط متنی ایندکس شدند.")
    return output, targets
