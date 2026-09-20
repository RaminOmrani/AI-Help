"""محصول‌های گروه میلیونر و تشخیصشان از روی چیزی که سامانه‌ی تیکت می‌فرستد.

هر سند در پنل مدیریت به یکی از این محصول‌ها بسته می‌شود. وقتی سامانه‌ی تیکت
سوالی می‌فرستد، فقط راهنمای همان محصول (به‌علاوه‌ی سندهای «همه‌ی محصولات»)
جستجو می‌شود؛ وگرنه ممکن است جوابِ منوکلاب از راهنمای حسابداری دربیاید.

اضافه کردن محصول پنجم: یک ردیف به PRODUCTS اضافه کنید. نام‌های مستعار را
دست‌ودل‌بازانه بنویسید — سامانه‌ی تیکت ممکن است «CRM میلیونر» یا
«میلیونر CRM» یا «milionar_crm» بفرستد و همه باید به یک محصول برسند.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .textutils import normalize  # همان نرمال‌سازی‌ای که جستجو استفاده می‌کند


@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    aliases: tuple[str, ...] = field(default=())


PRODUCTS: tuple[Product, ...] = (
    Product(
        slug="milionar",
        name="میلیونر",
        aliases=("نرم افزار میلیونر", "حسابداری میلیونر", "میلیونر حسابداری",
                 "milionar", "millionaire", "softmiliac"),
    ),
    Product(
        slug="milionar-crm",
        name="CRM میلیونر",
        aliases=("میلیونر CRM", "سی آر ام میلیونر", "crm", "milionar crm",
                 "milionar-crm", "milionar_crm", "crm-milionar"),
    ),
    Product(
        slug="menuclub",
        name="منوکلاب",
        aliases=("منو کلاب", "menu club", "menuclub", "menu-club"),
    ),
    Product(
        slug="shop-mojahaz",
        name="شاپ مجهز",
        aliases=("شاپ‌مجهز", "شاپ مجهز", "shop mojahaz", "shop-mojahaz",
                 "shopmojahaz", "mojahaz"),
    ),
)

# سندی که محصولش خالی بماند، مالِ همه‌ی محصول‌هاست (مثلاً راهنمای نصب مشترک).
ANY = ""

BY_SLUG = {p.slug: p for p in PRODUCTS}


def _keys(product: Product) -> set[str]:
    return {normalize(product.slug), normalize(product.name)} | {normalize(a) for a in product.aliases}


_LOOKUP: dict[str, Product] = {}
for _p in PRODUCTS:
    for _k in _keys(_p):
        if _k:
            _LOOKUP.setdefault(_k, _p)


def resolve(*candidates: str | None) -> Product | None:
    """اولین چیزی که به یک محصول می‌خورد را برمی‌گرداند.

    ترتیب مهم است: معمولاً company_slug دقیق‌تر از نام نمایشی است، پس
    اول آن را بدهید. اگر هیچ‌کدام نخورد None برمی‌گردد و صدازننده
    تصمیم می‌گیرد چه کند (ما در آن حالت روی همه‌ی محصول‌ها می‌گردیم).
    """
    for value in candidates:
        key = normalize(value or "")
        if not key:
            continue
        found = _LOOKUP.get(key)
        if found:
            return found
    return None


def is_valid(slug: str) -> bool:
    """آیا این اسلاگ یکی از محصول‌های شناخته‌شده است؟ (خالی هم مجاز است)"""
    return slug == ANY or slug in BY_SLUG


def as_options() -> list[dict]:
    """فهرست برای پنل مدیریت."""
    return [{"slug": ANY, "name": "همه‌ی محصولات"}] + [
        {"slug": p.slug, "name": p.name} for p in PRODUCTS
    ]


def display(slug: str) -> str:
    product = BY_SLUG.get(slug)
    return product.name if product else "همه‌ی محصولات"
