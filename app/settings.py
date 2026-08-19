"""تنظیمات قابل تغییر از پنل مدیریت.

هر مقدار اول از دیتابیس خوانده می‌شود و اگر آنجا نبود، از فایل `.env`.
یعنی می‌شود کلید و مدل‌ها را بدون دست زدن به فایل، از خود پنل عوض کرد —
ولی اگر کسی ترجیح می‌دهد همه چیز در `.env` باشد، آن هم مثل قبل کار می‌کند.
"""

from __future__ import annotations

import threading

from . import config, db

# نام تنظیم در دیتابیس → مقدار پیش‌فرض از .env
FIELDS: dict[str, str] = {
    "avalai_api_key": config.AVALAI_API_KEY,
    "chat_model": config.CHAT_MODEL,
    "fast_model": config.FAST_MODEL,
    "vision_model": config.VISION_MODEL,
    "embedding_model": config.EMBEDDING_MODEL,
    "vision_enabled": "true" if config.VISION_ENABLED else "false",
}

SECRET_FIELDS = {"avalai_api_key"}

_lock = threading.Lock()
_cache: dict[str, str] = {}
_loaded = False


def _load() -> dict[str, str]:
    global _loaded
    with _lock:
        if _loaded:
            return _cache
        _cache.clear()
        for name, fallback in FIELDS.items():
            stored = db.get_setting(f"ai.{name}", "")
            _cache[name] = stored.strip() or fallback
        _loaded = True
        return _cache


def invalidate() -> None:
    global _loaded
    with _lock:
        _loaded = False


def get(name: str) -> str:
    return _load().get(name, FIELDS.get(name, ""))


def save(values: dict[str, str]) -> None:
    """فقط کلیدهای شناخته‌شده ذخیره می‌شوند."""
    for name, value in values.items():
        if name not in FIELDS:
            continue
        db.set_setting(f"ai.{name}", (value or "").strip())
    invalidate()


# ------------------------------------------------------------------
# دسترسی‌های پرکاربرد
# ------------------------------------------------------------------
def api_key() -> str:
    return get("avalai_api_key")


def chat_model() -> str:
    return get("chat_model") or config.CHAT_MODEL


def fast_model() -> str:
    return get("fast_model") or chat_model()


def vision_model() -> str:
    return get("vision_model") or chat_model()


def embedding_model() -> str:
    return get("embedding_model") or config.EMBEDDING_MODEL


def vision_enabled() -> bool:
    return get("vision_enabled").lower() in {"1", "true", "yes", "on"}


def mask(secret: str) -> str:
    """نمایش امن کلید در پنل — هیچ‌وقت کلید کامل برنمی‌گردد."""
    if not secret:
        return ""
    if len(secret) <= 10:
        return "•" * len(secret)
    return f"{secret[:6]}{'•' * 10}{secret[-4:]}"


def public_view() -> dict:
    """چیزی که می‌شود با خیال راحت به پنل مدیریت فرستاد."""
    return {
        "api_key_masked": mask(api_key()),
        "api_key_set": bool(api_key()),
        "api_key_from_env": bool(config.AVALAI_API_KEY) and not db.get_setting("ai.avalai_api_key", ""),
        "chat_model": chat_model(),
        "fast_model": fast_model(),
        "vision_model": vision_model(),
        "embedding_model": embedding_model(),
        "vision_enabled": vision_enabled(),
    }
