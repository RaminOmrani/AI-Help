"""تنظیمات مرکزی پروژه — همه چیز از طریق متغیرهای محیطی قابل تغییر است."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key) or default)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key) or default)
    except ValueError:
        return default


# ------------------------------------------------------------------
# AvalAI  (https://avalai.ir)
# ------------------------------------------------------------------
AVALAI_API_KEY = _env("AVALAI_API_KEY")
AVALAI_BASE_URL = _env("AVALAI_BASE_URL", "https://api.avalai.ir/v1").rstrip("/")
# اندپوینت اعتبار خارج از /v1 است
AVALAI_CREDIT_URL = _env("AVALAI_CREDIT_URL", "https://api.avalai.ir/user/v1/credit")

CHAT_MODEL = _env("CHAT_MODEL", "gemini-3.7-flash")
FAST_MODEL = _env("FAST_MODEL", CHAT_MODEL)
VISION_MODEL = _env("VISION_MODEL", CHAT_MODEL)
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "text-embedding-3-large")
REQUEST_TIMEOUT = _env_float("REQUEST_TIMEOUT", 180.0)
# بردارسازیِ یک سوال باید سریع باشد؛ اگر کند شد بهتر است زود به جستجوی
# کلیدواژه‌ای برگردیم تا کاربر پشت یک درخواستِ گیرکرده منتظر نماند.
EMBED_TIMEOUT = _env_float("EMBED_TIMEOUT", 25.0)
EMBED_RETRIES = _env_int("EMBED_RETRIES", 2)

# سقف طول پاسخ — فقط محافظ در برابر پاسخ‌های افسارگسیخته است، نه ابزار کنترل طول.
# طول واقعی را پرامپت تعیین می‌کند تا پاسخ هیچ‌وقت وسط جمله قطع نشود.
ANSWER_MAX_TOKENS = _env_int("ANSWER_MAX_TOKENS", 4000)

# ------------------------------------------------------------------
# مسیرها
# ------------------------------------------------------------------
DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR / "data")))
DOCS_DIR = Path(_env("DOCS_DIR", str(BASE_DIR / "docs")))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = Path(_env("DB_PATH", str(DATA_DIR / "support.db")))
WEB_DIR = BASE_DIR / "web"

for _p in (DATA_DIR, UPLOAD_DIR, DOCS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# RAG
# ------------------------------------------------------------------
CHUNK_CHARS = _env_int("CHUNK_CHARS", 900)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 160)
TOP_K = _env_int("TOP_K", 8)
EMBED_BATCH = _env_int("EMBED_BATCH", 48)
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 60)

# ------------------------------------------------------------------
# خواندن تصویری صفحه‌های PDF (اسکرین‌شات‌ها)
# ------------------------------------------------------------------
VISION_ENABLED = _env("VISION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
VISION_DPI = _env_int("VISION_DPI", 120)
VISION_JPEG_QUALITY = _env_int("VISION_JPEG_QUALITY", 85)
VISION_MAX_PAGES = _env_int("VISION_MAX_PAGES", 300)
VISION_CONCURRENCY = _env_int("VISION_CONCURRENCY", 3)

# ------------------------------------------------------------------
# امنیت
# ------------------------------------------------------------------
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "admin")
AGENT_PASSWORD = _env("AGENT_PASSWORD", "support")
SECRET_KEY = _env("SECRET_KEY", "change-me-please")
SESSION_HOURS = _env_int("SESSION_HOURS", 24)

# ------------------------------------------------------------------
# برند
# ------------------------------------------------------------------
BRAND_NAME = _env("BRAND_NAME", "میلیونر")
BRAND_PRODUCT = _env("BRAND_PRODUCT", "نرم‌افزار حسابداری و فروشگاهی میلیونر")
ASSISTANT_NAME = _env("ASSISTANT_NAME", "میلی")
SUPPORT_PHONE = _env("SUPPORT_PHONE", "")
SUPPORT_HOURS = _env("SUPPORT_HOURS", "شنبه تا چهارشنبه، ۹ تا ۱۷")

# ------------------------------------------------------------------
# انتشار روی اینترنت
# ------------------------------------------------------------------
# دامنه‌هایی که اجازه دارند از مرورگر به این API وصل شوند.
# خالی یعنی «همه» — فقط برای اجرای محلی مناسب است.
ALLOWED_ORIGINS = [o.strip() for o in _env("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# اگر پشت nginx / کلادفلر هستید true بگذارید تا آی‌پی واقعی کاربر از هدر خوانده شود.
# اگر مستقیم در معرض اینترنت هستید حتماً false بماند، وگرنه هدر جعل می‌شود.
TRUST_PROXY = _env("TRUST_PROXY", "false").lower() in {"1", "true", "yes", "on"}

# محافظ اعتبار: سقف سوال برای هر آی‌پی
RATE_LIMIT_ENABLED = _env("RATE_LIMIT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
RATE_LIMIT_PER_MINUTE = _env_int("RATE_LIMIT_PER_MINUTE", 10)
RATE_LIMIT_PER_DAY = _env_int("RATE_LIMIT_PER_DAY", 150)

HOST = _env("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)
# باز کردن خودکار مرورگر — فقط برای اجرای روی کامپیوتر شخصی
OPEN_BROWSER = _env("OPEN_BROWSER", "false").lower() in {"1", "true", "yes", "on"}
