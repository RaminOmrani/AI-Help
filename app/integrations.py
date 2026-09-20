"""اتصال سرور-به-سرور — پاسخ‌دهی به سامانه‌ی تیکت.

فرق این مسیر با صفحه‌ی مشتری:
  • احراز هویت با یک کلید ثابت در هدر Authorization، نه کد دسترسی.
  • بدون استریم؛ یک JSON با کلید `reply` برمی‌گردد.
  • سابقه‌ی گفتگو را خودِ سامانه‌ی تیکت در `messages` می‌فرستد، پس اینجا
    نشست و کوکی و شناسه‌ی مرورگر در کار نیست.
  • جستجو به محصولی که در metadata آمده محدود می‌شود.

پاسخ برای **مشتری** نوشته می‌شود، نه برای کارشناس: جواب تیکت در نهایت به
دست مشتری می‌رسد، پس همان خط قرمزهای صفحه‌ی مشتری اینجا هم برقرار است و
هیچ ارجاع داخلی، رمز یا دستور SQL در آن نمی‌آید. اگر سامانه‌ای عمداً پاسخ
فنیِ کارشناس‌پسند بخواهد، می‌تواند در metadata مقدار `"audience": "internal"`
بفرستد — آن وقت پاسخ مثل کنسول پشتیبان می‌شود و **نباید** مستقیم برای
مشتری فرستاده شود.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException

from . import avalai, config, db, products, prompts, rag, settings

# چند پیام آخر از سابقه‌ای که سامانه می‌فرستد به مدل داده می‌شود.
# بیشتر از این، هم هزینه‌ی توکن دارد و هم معمولاً به دقت پاسخ کمکی نمی‌کند.
HISTORY_TURNS = 6
MAX_MESSAGE_CHARS = 8000


def key_from_header(authorization: str | None) -> str:
    """کلید داخل هدر Authorization، اگر اصلاً چیزی آمده باشد."""
    value = (authorization or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def is_integration_request(authorization: str | None) -> bool:
    """آیا این درخواست با یکی از کلیدهای سامانه‌های داخلی آمده است؟"""
    key = key_from_header(authorization)
    return bool(key) and settings.integration_key_is_valid(key)


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def parse_messages(raw: Any) -> tuple[str, list[dict]]:
    """آخرین سوال کاربر و سابقه‌ی پیش از آن را جدا می‌کند."""
    if not isinstance(raw, list) or not raw:
        raise _bad("فیلد messages باید یک آرایه‌ی غیرخالی باشد.")

    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise _bad("هر عضو messages باید یک شیء با role و content باشد.")
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "") or "").strip()
        if role not in {"user", "assistant"}:
            raise _bad("مقدار role فقط می‌تواند user یا assistant باشد.")
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})

    if not cleaned:
        raise _bad("هیچ پیام غیرخالی‌ای در messages نبود.")
    if cleaned[-1]["role"] != "user":
        raise _bad("آخرین پیام باید از طرف user باشد تا بشود جوابش را داد.")

    question = cleaned[-1]["content"]
    history = cleaned[:-1][-HISTORY_TURNS:]
    return question, history


def _context_note(meta: dict, product: products.Product | None) -> str:
    """یک خط توضیح درباره‌ی اینکه این سوال از کجا آمده است."""
    company = str(meta.get("company", "") or "").strip()
    department = str(meta.get("department", "") or "").strip()
    user_name = str(meta.get("user_name", "") or "").strip()

    bits = []
    if product:
        bits.append(f"محصول: {product.name}")
    elif company:
        bits.append(f"محصول: {company}")
    if department:
        bits.append(f"دپارتمان: {department}")
    if user_name:
        bits.append(f"نام کاربر: {user_name}")
    if not bits:
        return ""
    return (
        "این سوال از سامانه‌ی تیکت آمده است — "
        + "، ".join(bits)
        + ".\nفقط درباره‌ی همین محصول جواب بده و محصول دیگری را با آن قاطی نکن."
    )


async def answer(payload: dict, *, key: str) -> dict:
    """پاسخ به یک درخواست سامانه‌ی تیکت."""
    started = time.time()

    if not isinstance(payload, dict):
        raise _bad("بدنه‌ی درخواست باید JSON باشد.")
    meta = payload.get("metadata") or {}
    if not isinstance(meta, dict):
        raise _bad("فیلد metadata باید یک شیء باشد.")

    question, history = parse_messages(payload.get("messages"))

    if not settings.api_key():
        raise HTTPException(
            status_code=503,
            detail="کلید AvalAI روی سرور ثبت نشده است؛ فعلاً پاسخی تولید نمی‌شود.",
        )

    # company_slug دقیق‌تر است، پس اول امتحان می‌شود
    product = products.resolve(meta.get("company_slug"), meta.get("company"))

    # پیش‌فرض: پاسخ برای مشتری. جواب تیکت به دست مشتری می‌رسد.
    audience = "internal" if str(meta.get("audience", "")).strip() == "internal" else "public"

    try:
        hits = await rag.search(
            question,
            audience=audience,
            product=product.slug if product else None,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"جستجو در مستندات ناموفق بود: {avalai.describe(exc)}"
        ) from exc

    context = rag.build_context(hits)
    system = prompts.customer_system() if audience == "public" else prompts.agent_system()
    note = _context_note(meta, product)
    if note:
        system = f"{system}\n\n{note}"

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({
        "role": "user",
        "content": prompts.user_turn(question, context, audience=audience, length="normal"),
    })

    stream_meta: dict = {}
    try:
        reply = await avalai.chat(
            messages,
            temperature=0.2 if audience == "internal" else 0.35,
            max_tokens=config.ANSWER_MAX_TOKENS,
            meta=stream_meta,
        )
    except avalai.AvalAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    reply = (reply or "").strip()
    if not reply:
        raise HTTPException(status_code=502, detail="پاسخی از مدل دریافت نشد.")

    truncated = stream_meta.get("finish_reason") == "length"
    if truncated:
        reply += "\n\n⚠️ پاسخ به سقف طول رسید و ممکن است ناقص باشد."

    latency = int((time.time() - started) * 1000)
    grounded = bool(hits)

    db.execute(
        "INSERT INTO integration_calls"
        "(company, product, department, user_name, question, answer, grounded, latency_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(meta.get("company", "") or "")[:120],
            product.slug if product else "",
            str(meta.get("department", "") or "")[:120],
            str(meta.get("user_name", "") or "")[:120],
            question[:2000],
            reply[:8000],
            1 if grounded else 0,
            latency,
        ),
    )

    return {
        "reply": reply,
        # فیلدهای کمکی؛ سامانه می‌تواند نادیده‌شان بگیرد.
        # matched_product اگر خالی بود یعنی company شناخته نشد و جستجو روی
        # همه‌ی محصول‌ها انجام شده — جای بررسی دارد.
        "matched_product": product.slug if product else "",
        "grounded": grounded,
        "truncated": truncated,
        "latency_ms": latency,
    }


def limits() -> tuple[int, int]:
    return config.INTEGRATION_RATE_PER_MINUTE, config.INTEGRATION_RATE_PER_DAY
