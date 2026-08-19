"""تست سلامت اتصال به AvalAI — مشترک بین پنل مدیریت و اسکریپت ترمینال."""

from __future__ import annotations

import base64

from . import avalai, settings


def sample_image() -> str:
    """تصویر کوچکی با عدد ۱۲۳۴ برای تست خواندن تصویر."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=260, height=120)
    page.insert_text((40, 75), "1234", fontsize=54)
    png = page.get_pixmap(dpi=110).tobytes("png")
    doc.close()
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _check(name: str, ok: bool, detail: str = "", hint: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "hint": hint}


async def check_key() -> dict:
    if not settings.api_key():
        return _check(
            "کلید API", False,
            "کلیدی ثبت نشده است.",
            "کلید را از avalai.ir بگیرید و همین‌جا وارد کنید.",
        )
    return _check("کلید API", True, settings.mask(settings.api_key()))


async def check_credit() -> dict:
    try:
        data = await avalai.credit()
    except Exception as exc:  # noqa: BLE001
        return _check("اعتبار حساب", False, str(exc)[:200])

    irt = float(data.get("remaining_irt") or 0)
    unit = float(data.get("total_unit") or data.get("remaining_unit") or 0)
    detail = f"{irt:,.0f} تومان | {unit:.2f} واحد"
    if irt <= 0 and unit <= 0:
        return _check("اعتبار حساب", False, detail, "اعتبار صفر است؛ درخواست‌ها رد می‌شوند.")
    return _check("اعتبار حساب", True, detail)


async def check_chat() -> dict:
    model = settings.chat_model()
    try:
        answer = await avalai.chat(
            [{"role": "user", "content": "فقط بنویس: سلام"}], model=model, max_tokens=20
        )
    except Exception as exc:  # noqa: BLE001
        return _check(
            f"مدل پاسخ‌دهی ({model})", False, str(exc)[:200],
            "نام مدل را بررسی کنید؛ ممکن است روی حساب شما فعال نباشد.",
        )
    return _check(f"مدل پاسخ‌دهی ({model})", True, answer[:60])


async def check_vision() -> dict:
    model = settings.vision_model()
    if not settings.vision_enabled():
        return _check(f"مدل بینایی ({model})", True, "خاموش است — اسکرین‌شات‌ها خوانده نمی‌شوند.")
    try:
        answer = await avalai.chat(
            [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": sample_image()}},
                    {"type": "text", "text": "فقط عددی که در تصویر نوشته شده را بنویس."},
                ],
            }],
            model=model,
            max_tokens=30,
        )
    except Exception as exc:  # noqa: BLE001
        return _check(
            f"مدل بینایی ({model})", False, str(exc)[:200],
            "مدلی انتخاب کنید که تصویر می‌فهمد (Gemini، GPT-5.x، Claude).",
        )

    if "1234" in answer.replace("۱۲۳۴", "1234"):
        return _check(f"مدل بینایی ({model})", True, "تصویر آزمایشی درست خوانده شد.")
    return _check(
        f"مدل بینایی ({model})", False, f"پاسخ نادرست: {answer[:60]}",
        "این مدل تصویر را درست نمی‌خواند؛ اسکرین‌شات‌های PDF از دست می‌روند.",
    )


async def check_embedding() -> dict:
    model = settings.embedding_model()
    try:
        vectors = await avalai.embed(["تست جستجوی معنایی"], model=model)
    except Exception as exc:  # noqa: BLE001
        return _check(
            f"مدل بردارسازی ({model})", False, str(exc)[:200],
            "بدون بردارسازی، جستجو فقط کلیدواژه‌ای می‌شود (کیفیت پایین‌تر).",
        )
    return _check(f"مدل بردارسازی ({model})", True, f"بُعد بردار: {len(vectors[0])}")


async def run_checks() -> list[dict]:
    """همه‌ی تست‌ها به ترتیب. اگر کلید نباشد، بقیه اجرا نمی‌شوند."""
    key = await check_key()
    if not key["ok"]:
        return [key]
    results = [key]
    for check in (check_credit, check_chat, check_vision, check_embedding):
        results.append(await check())
    return results
