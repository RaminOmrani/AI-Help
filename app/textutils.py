"""ابزارهای متن فارسی: نرمال‌سازی و ترمیم متنِ استخراج‌شده از PDF."""

from __future__ import annotations

import re

ZWNJ = "‌"

# نگاشت حروف عربی/نویسه‌های مشابه به معادل استاندارد فارسی
_CHAR_MAP = {
    "ي": "ی",  # ي -> ی
    "ى": "ی",  # ى -> ی
    "ك": "ک",  # ك -> ک
    "ڪ": "ک",
    "ة": "ه",  # ة -> ه
    "ؤ": "و",  # ؤ -> و
    "ئ": "ی",  # ئ -> ی
    "إ": "ا",
    "أ": "ا",
    "آ": "ا",  # آ -> ا (فقط در نرمال‌سازیِ جستجو)
    "ـ": "",        # کشیدگی
    "‏": "",
    "‎": "",
    "﻿": "",
}

# اعراب و علائم تشکیل
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭ]")

# ارقام عربی/فارسی -> لاتین
_DIGITS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})

_LAM_ALEF = "\ufefb"  # نویسه‌ی جایگزین برای ترکیب لام-الف
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+")

# ------------------------------------------------------------------
# ترمیم لیگاتور «لا» که در بسیاری از PDFها برعکس استخراج می‌شود («ال»)
# ------------------------------------------------------------------
_LIGATURE_FIXES: list[tuple[str, str]] = [
    ("کاال", "کالا"),
    ("باال", "بالا"),
    ("اطالع", "اطلاع"),
    ("مشکال", "مشکلا"),
    ("سواال", "سوالا"),
    ("خالصه", "خلاصه"),
    ("آنالین", "آنلاین"),
    ("انالین", "آنلاین"),
    ("آفالین", "آفلاین"),
    ("افالین", "آفلاین"),
    ("عالمت", "علامت"),
    ("عالئم", "علائم"),
    ("معموال", "معمولا"),
    ("کالینت", "کلاینت"),
    ("اصالح", "اصلاح"),
    ("تالش", "تلاش"),
    ("مالحظه", "ملاحظه"),
    ("اعالم", "اعلام"),
    ("استعالم", "استعلام"),
    ("اسالید", "اسلاید"),
    ("پالگین", "پلاگین"),
    ("میالدی", "میلادی"),
    ("حاال", "حالا"),
    ("اضافال", "اضافه‌لا"),
    ("طالعات", "طلاعات"),
    ("اشتال", "اشتلا"),
]

# کلماتی که فقط به صورت مستقل باید ترمیم شوند (وگرنه واژه‌های درست را خراب می‌کنند)
_LIGATURE_WORD_FIXES: dict[str, str] = {
    "الزم": "لازم",
    "الزمه": "لازمه",
    "کال": "کلا",
    "اصال": "اصلا",
    "کامال": "کاملا",
    "قبال": "قبلا",
    "بعال": "بعلا",
    "فعال‌سازی": "فعال‌سازی",
    "الگ": "لاگ",
    "الین": "لاین",
    "دالر": "دلار",
    "کالس": "کلاس",
    "پالک": "پلاک",
    "کالم": "کلام",
    "اطالعات": "اطلاعات",
    "احتماال": "احتمالا",
    "متقابال": "متقابلا",
    "مستقال": "مستقلا",
}

_WORD_RE = re.compile(r"[\w؀-ۿ‌]+", flags=re.UNICODE)


def repair_pdf_text(text: str) -> str:
    """ترمیم واژه‌های رایجی که به خاطر لیگاتور «لا» بد استخراج شده‌اند."""
    if not text:
        return ""

    def _fix_word(match: re.Match[str]) -> str:
        word = match.group(0)
        if word in _LIGATURE_WORD_FIXES:
            return _LIGATURE_WORD_FIXES[word]
        return word

    text = _WORD_RE.sub(_fix_word, text)
    for broken, correct in _LIGATURE_FIXES:
        if broken in text:
            text = text.replace(broken, correct)
    return text


def clean_text(text: str) -> str:
    """پاک‌سازی سبک برای نمایش و ارسال به مدل (بدون از بین بردن ساختار)."""
    text = text.replace("‏", "").replace("‎", "")
    text = _DIACRITICS.sub("", text)
    text = repair_pdf_text(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


def normalize(text: str) -> str:
    """نرمال‌سازی تهاجمی برای جستجوی لغوی."""
    if not text:
        return ""
    text = _DIACRITICS.sub("", text)
    text = text.translate(_DIGITS)
    for src, dst in _CHAR_MAP.items():
        text = text.replace(src, dst)
    text = text.replace(ZWNJ, " ")
    # «لا» و «ال» هر دو به یک نویسه‌ی واحد تبدیل می‌شوند تا خطای استخراج PDF اثر نگذارد
    text = text.replace("لا", _LAM_ALEF).replace("ال", _LAM_ALEF)
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip().lower()


_STOPWORDS = {
    "از", "به", "با", "در", "را", "که", "این", "آن", "و", "یا", "برای", "است",
    "هست", "می", "شود", "کنم", "کنید", "چطور", "چگونه", "چه", "کار", "بر", "تا",
    "هم", "اگر", "ولی", "اما", "بود", "شد", "های", "ها", "یک", "من", "ما", "شما",
    "کردن", "کرد", "دارد", "دارم", "باید", "نیست", "کنیم", "the", "a", "an", "of",
    "to", "in", "is", "how", "what", "and", "for",
}


def tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if len(t) > 1 and t not in _STOPWORDS]


def snippet(text: str, limit: int = 220) -> str:
    text = _SPACES.sub(" ", text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"
