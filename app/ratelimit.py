"""محدودسازی نرخ درخواست — محافظ اعتبار AvalAI روی اینترنت عمومی.

صفحه‌ی مشتری باز است و هر کسی می‌تواند سوال بپرسد. بدون این محافظ، یک ربات
یا یک نفر شوخ می‌تواند در چند دقیقه کل اعتبار حساب را بسوزاند.

شمارنده در حافظه نگه داشته می‌شود که برای یک سرور تک‌پروسسی کافی است.
اگر روزی چند نگهبان (worker) اجرا کردید، این شمارنده بین آن‌ها مشترک نیست و
باید سراغ Redis بروید.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

_lock = threading.Lock()
_minute: dict[str, deque[float]] = defaultdict(deque)
_day: dict[str, deque[float]] = defaultdict(deque)
_last_sweep = 0.0

MINUTE = 60
DAY = 24 * 60 * 60


def client_ip(request: Request) -> str:
    """آی‌پی واقعی کاربر.

    وقتی پشت nginx یا کلادفلر هستیم، آی‌پیِ اتصال همیشه ۱۲۷.۰.۰.۱ است و
    آی‌پی واقعی در هدر می‌آید. این هدر را فقط وقتی باور می‌کنیم که صریحاً
    گفته باشیم پشت پراکسی هستیم — وگرنه هر کسی می‌تواند جعلش کند و از
    محدودیت فرار کند.
    """
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real = request.headers.get("x-real-ip", "")
        if real:
            return real.strip()
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    """پاک کردن آی‌پی‌های قدیمی تا حافظه بی‌نهایت رشد نکند."""
    global _last_sweep
    if now - _last_sweep < 300:
        return
    _last_sweep = now
    for store, window in ((_minute, MINUTE), (_day, DAY)):
        for key in [k for k, v in store.items() if not v or now - v[-1] > window]:
            store.pop(key, None)


def _hit(store: dict[str, deque[float]], key: str, window: int, limit: int, now: float) -> bool:
    """آیا این درخواست در سقف جا می‌شود؟ اگر بله، ثبتش می‌کند."""
    bucket = store[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def check(request: Request, *, cost: int = 1) -> None:
    """اگر کاربر از سقف رد شده باشد، خطای ۴۲۹ می‌دهد."""
    if not config.RATE_LIMIT_ENABLED:
        return

    ip = client_ip(request)
    now = time.time()

    with _lock:
        _sweep(now)
        for _ in range(cost):
            if not _hit(_minute, ip, MINUTE, config.RATE_LIMIT_PER_MINUTE, now):
                raise HTTPException(
                    status_code=429,
                    detail="تعداد سوال‌ها در دقیقه زیاد شد. چند لحظه صبر کنید و دوباره بپرسید.",
                    headers={"Retry-After": "30"},
                )
            if not _hit(_day, ip, DAY, config.RATE_LIMIT_PER_DAY, now):
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "سقف سوال‌های امروز شما پر شد. "
                        "برای ادامه با پشتیبانی تماس بگیرید."
                    ),
                    headers={"Retry-After": "3600"},
                )


def snapshot() -> dict:
    """آماری برای پنل مدیریت."""
    with _lock:
        now = time.time()
        active = sum(1 for v in _minute.values() if v and now - v[-1] < MINUTE)
        today = sum(len(v) for v in _day.values())
    return {
        "enabled": config.RATE_LIMIT_ENABLED,
        "per_minute": config.RATE_LIMIT_PER_MINUTE,
        "per_day": config.RATE_LIMIT_PER_DAY,
        "active_visitors": active,
        "requests_today": today,
    }
