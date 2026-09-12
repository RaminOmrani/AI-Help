"""احراز هویت ساده و بدون وابستگی: توکن امضاشده با HMAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException

from . import config

ROLE_PASSWORDS = {
    "admin": lambda: config.ADMIN_PASSWORD,
    "agent": lambda: config.AGENT_PASSWORD,
}


def constant_time_equals(given: str | None, expected: str | None) -> bool:
    """مقایسه‌ی رمز در زمان ثابت، بدون فرض ASCII بودن.

    hmac.compare_digest روی رشته فقط با نویسه‌های ASCII کار می‌کند و اگر کاربر
    حتی یک حرف فارسی تایپ کند TypeError می‌دهد. با تبدیل به بایت هم رمز فارسی
    پشتیبانی می‌شود و هم مقایسه در زمان ثابت باقی می‌ماند.
    """
    return hmac.compare_digest((given or "").encode("utf-8"), (expected or "").encode("utf-8"))


def _sign(payload: bytes) -> str:
    digest = hmac.new(config.SECRET_KEY.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(role: str, *, hours: int | None = None) -> str:
    lifetime = (hours or config.SESSION_HOURS) * 3600
    payload = json.dumps({"role": role, "exp": int(time.time()) + lifetime}).encode()
    body = _b64(payload)
    return f"{body}.{_sign(payload)}"


def verify_token(token: str) -> str | None:
    """نقش کاربر را برمی‌گرداند یا None."""
    try:
        body, signature = token.split(".", 1)
        payload = _unb64(body)
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("role")


def login(role: str, password: str) -> str:
    getter = ROLE_PASSWORDS.get(role)
    if not getter:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است.")
    expected = getter()
    if not expected or not constant_time_equals(password, expected):
        raise HTTPException(status_code=401, detail="رمز عبور اشتباه است.")
    return create_token(role)


def _extract(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="ابتدا وارد شوید.")
    return authorization.removeprefix("Bearer ").strip()


async def require_admin(authorization: str | None = Header(default=None)) -> str:
    role = verify_token(_extract(authorization))
    if role != "admin":
        raise HTTPException(status_code=403, detail="دسترسی مدیر لازم است.")
    return role


async def require_visitor(authorization: str | None = Header(default=None)) -> str:
    """دسترسی به صفحه‌ی مشتری.

    وقتی حالت روی «open» است هیچ چیزی لازم نیست. وقتی روی «code» است،
    کاربر باید یک بار کد دسترسی را وارد کرده و توکن مهمان گرفته باشد.
    کارکنان (مدیر و کارشناس) هم طبیعتاً اجازه دارند.
    """
    from . import settings

    if settings.access_mode() == "open":
        return "public"

    token = (authorization or "").removeprefix("Bearer ").strip()
    role = verify_token(token) if token else None
    if role in {"visitor", "agent", "admin"}:
        return role
    raise HTTPException(
        status_code=401,
        detail="برای استفاده از دستیار، کد دسترسی لازم است.",
    )


async def require_staff(authorization: str | None = Header(default=None)) -> str:
    """پشتیبان یا مدیر."""
    role = verify_token(_extract(authorization))
    if role not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="دسترسی کارشناس پشتیبانی لازم است.")
    return role


# ------------------------------------------------------------------
# بررسی آمادگی برای انتشار عمومی
# ------------------------------------------------------------------
INSECURE_DEFAULTS = {
    "ADMIN_PASSWORD": "admin",
    "AGENT_PASSWORD": "support",
    "SECRET_KEY": "change-me-please",
}

# مقادیری که در فایل نمونه نوشته شده‌اند و کاربر یادش رفته عوضشان کند.
# طولشان کافی است ولی تصادفی نیستند، پس نباید «امن» حساب شوند.
PLACEHOLDERS = {
    "یک-رشته-تصادفی-طولانی",
    "یک-رشته-تصادفی-طولانی-اینجا-بگذارید",
    "رمز-مدیر",
    "رمز-کارشناس",
    "changeme",
    "change-me",
    "your-secret-key",
    "aa-xxxxxxxxxxxxxxxxxxxxxxxx",
}


def is_placeholder(value: str) -> bool:
    """آیا این مقدار هنوز همان چیزی است که در فایل نمونه بود؟"""
    cleaned = (value or "").strip()
    if cleaned in PLACEHOLDERS:
        return True
    # مقادیر نمونه معمولاً فقط حرف و خط تیره‌اند و هیچ تصادفی‌بودنی ندارند
    return bool(cleaned) and cleaned.count("-") >= 3 and not any(c.isdigit() for c in cleaned)


def security_issues() -> list[dict]:
    """مشکل‌هایی که قبل از باز کردن سایت روی اینترنت باید حل شوند."""
    issues: list[dict] = []

    if config.ADMIN_PASSWORD == INSECURE_DEFAULTS["ADMIN_PASSWORD"] or is_placeholder(config.ADMIN_PASSWORD):
        issues.append({
            "key": "ADMIN_PASSWORD",
            "text": "رمز پنل مدیریت هنوز «admin» است — هر کسی می‌تواند وارد شود و کلید API را عوض کند.",
        })
    if config.AGENT_PASSWORD == INSECURE_DEFAULTS["AGENT_PASSWORD"] or is_placeholder(config.AGENT_PASSWORD):
        issues.append({
            "key": "AGENT_PASSWORD",
            "text": "رمز کنسول پشتیبان هنوز «support» است — مستندات داخلی در دسترس عموم قرار می‌گیرد.",
        })
    if config.SECRET_KEY == INSECURE_DEFAULTS["SECRET_KEY"] or is_placeholder(config.SECRET_KEY):
        issues.append({
            "key": "SECRET_KEY",
            "text": "SECRET_KEY هنوز مقدار نمونه است — توکن ورود قابل جعل می‌شود.",
        })
    elif len(config.SECRET_KEY) < 32:
        issues.append({
            "key": "SECRET_KEY_SHORT",
            "text": "SECRET_KEY کوتاه است؛ حداقل ۳۲ نویسه‌ی تصادفی بگذارید.",
        })
    if not config.ALLOWED_ORIGINS:
        issues.append({
            "key": "ALLOWED_ORIGINS",
            "text": "ALLOWED_ORIGINS خالی است — هر سایتی می‌تواند از مرورگر به این API وصل شود.",
        })
    if not config.RATE_LIMIT_ENABLED:
        issues.append({
            "key": "RATE_LIMIT",
            "text": "محدودیت نرخ خاموش است — اعتبار AvalAI بی‌محافظ می‌ماند.",
        })
    return issues


def print_startup_warnings() -> None:
    """هشدارهای امنیتی را هنگام بالا آمدن سرور در کنسول نشان می‌دهد."""
    issues = security_issues()
    if not issues:
        return
    print("  " + "─" * 54)
    print(f"  ⚠️  {len(issues)} مورد امنیتی — برای اجرای محلی اشکالی ندارد،")
    print("      ولی قبل از باز کردن روی اینترنت حتماً درستشان کنید:")
    for issue in issues:
        print(f"      • {issue['text']}")
    print("      راهنما: DEPLOY.md  |  بررسی: python scripts/preflight.py")
    print("  " + "─" * 54)
