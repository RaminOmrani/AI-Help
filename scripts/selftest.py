"""تست سلامت خط لوله، بدون نیاز به کلید یا اینترنت.

سرویس AvalAI با یک نسخه‌ی ساختگی جایگزین می‌شود تا بشود بدون هزینه بررسی کرد که
ایندکس‌گذاری، تفکیک دسترسی مشتری/پشتیبان، استریم پاسخ و ذخیره‌ی گفتگو درست کار می‌کنند.

    python scripts/selftest.py
"""

import asyncio
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORK = Path(tempfile.mkdtemp(prefix="support-ai-selftest-"))
os.environ['DB_PATH'] = str(WORK / 'test.db')
os.environ['DATA_DIR'] = str(WORK)
os.environ['DOCS_DIR'] = str(WORK / 'docs')
os.environ['AVALAI_API_KEY'] = 'aa-fake-key-for-testing'

from app import (  # noqa: E402
    avalai, chat_service, config, db, integrations, products, rag, repair, settings, vision,
)

calls = {"chat": 0, "embed": 0, "stream": 0, "vision": 0, "image_bytes": [], "max_tokens": None}


def fake_vector(text, dim=64):
    """بردار قطعی بر پایه‌ی کلمات — تا شباهت معنایی قابل تست باشد."""
    vec = [0.0] * dim
    for word in text.split():
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    return vec


async def fake_embed(texts, model=None):
    calls["embed"] += 1
    return [fake_vector(t) for t in texts]


async def fake_chat(messages, model=None, temperature=0.0, max_tokens=None, meta=None):
    calls["chat"] += 1
    user = messages[-1]["content"]
    # درخواست بینایی: محتوا لیستی شامل تصویر است
    if isinstance(user, list):
        image = next((c for c in user if c.get("type") == "image_url"), None)
        assert image, "تصویری به مدل بینایی نرسید"
        url = image["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,"), "قالب تصویر درست نیست"
        raw = base64.b64decode(url.split(",", 1)[1])
        assert raw[:3] == b"\xff\xd8\xff", "تصویر JPEG معتبر نیست"
        calls["vision"] += 1
        calls["image_bytes"].append(len(raw))
        return "متن تمیزشده‌ی صفحه.\n\nتصویر: پنجره‌ی Welcome نصب SQL Server — دکمه‌ی Next را بزنید."
    if messages[0]["content"].startswith("تو یک ابزار بازسازی"):
        return user.replace("سواالت", "سوالات").replace("کاال", "کالا")
    return "پاسخ ساختگی"


async def fake_stream(messages, model=None, temperature=0.0, max_tokens=None, meta=None):
    calls["stream"] += 1
    context = messages[-1]["content"]
    assert "### مستندات" in context, "بلوک مستندات به مدل نرسید"
    assert "کامل تمام کن" in context, "دستور «پاسخ را کامل تمام کن» به مدل نرسید"
    calls["max_tokens"] = max_tokens
    for piece in ["۱. ", "منوی فروش ", "را باز کنید.\n", "۲. دکمه‌ی جدید را بزنید."]:
        yield piece
    if meta is not None:
        meta["finish_reason"] = "stop"


avalai.embed = fake_embed
avalai.chat = fake_chat
avalai.chat_stream = fake_stream
repair.avalai.chat = fake_chat
vision.avalai.chat = fake_chat
rag.avalai.embed = fake_embed
chat_service.avalai.chat_stream = fake_stream
integrations.avalai.chat = fake_chat


async def check_integration() -> bool:
    """سوالِ هر محصول فقط از راهنمای خودش جواب بگیرد."""
    passed = True

    menu = str(WORK / 'menu.txt')
    shop = str(WORK / 'shop.txt')
    common = str(WORK / 'common.txt')
    open(menu, 'w', encoding='utf-8').write(
        "چطور منوی دیجیتال رستوران را بسازم؟\nاز بخش مدیریت منو، دکمه‌ی افزودن دسته را بزنید.\n" * 4)
    open(shop, 'w', encoding='utf-8').write(
        "چطور محصول فروشگاه را منتشر کنم؟\nاز بخش محصولات، دکمه‌ی انتشار را بزنید.\n" * 4)
    open(common, 'w', encoding='utf-8').write(
        "برای تغییر رمز عبور حساب کاربری، از تنظیمات پروفایل اقدام کنید.\n" * 4)

    ids = {}
    for slug, title, path in (
        ("menuclub", "راهنمای منوکلاب", menu),
        ("shop-mojahaz", "راهنمای شاپ مجهز", shop),
        ("", "راهنمای مشترک", common),
    ):
        ids[slug] = db.execute(
            "INSERT INTO documents(title, filename, path, audience, product, size_bytes) "
            "VALUES (?,?,?,?,?,?)",
            (title, Path(path).name, path, "both", slug, os.path.getsize(path)))
        await rag.index_document(ids[slug])

    # جستجوی محدود به یک محصول نباید سند محصول دیگر را برگرداند
    hits = await rag.search("چطور محصول را منتشر کنم؟", audience="public", product="menuclub")
    if any(h.doc_id == ids["shop-mojahaz"] for h in hits):
        print("❌ راهنمای شاپ مجهز در جستجوی منوکلاب ظاهر شد!"); passed = False
    else:
        print("✅ جستجوی هر محصول فقط در راهنمای خودش انجام می‌شود")

    # سند «همه‌ی محصولات» باید برای هر محصولی دیده شود
    shared = await rag.search("تغییر رمز عبور حساب کاربری", audience="public", product="menuclub")
    assert any(h.doc_id == ids[""] for h in shared), "سند مشترک برای محصول دیده نشد"
    print("✅ سند «همه‌ی محصولات» برای هر محصولی در دسترس است")

    # نام شرکت و اسلاگ هر دو باید به یک محصول برسند
    assert products.resolve("menuclub").slug == "menuclub"
    assert products.resolve(None, "منوکلاب").slug == "menuclub"
    assert products.resolve("CRM میلیونر").slug == "milionar-crm"
    assert products.resolve("شرکت ناشناس") is None
    print("✅ تشخیص محصول از روی نام و اسلاگ کار می‌کند")

    # پاسخ کامل اندپوینت
    result = await integrations.answer({
        "messages": [
            {"role": "user", "content": "سلام"},
            {"role": "assistant", "content": "سلام، بفرمایید"},
            {"role": "user", "content": "چطور منوی دیجیتال بسازم؟"},
        ],
        "metadata": {
            "company": "منوکلاب", "company_slug": "menuclub",
            "department": "پشتیبانی فنی", "user_name": "رامین",
        },
    }, key="test")
    assert result["reply"], "پاسخ خالی برگشت"
    assert result["matched_product"] == "menuclub", result["matched_product"]
    print(f"✅ اندپوینت سامانه‌ی تیکت پاسخ داد (محصول: {result['matched_product']})")

    logged = db.query_one(
        "SELECT company, product, department, user_name FROM integration_calls ORDER BY id DESC LIMIT 1")
    assert logged["product"] == "menuclub" and logged["department"] == "پشتیبانی فنی", dict(logged)
    print("✅ تماس سامانه در جدول حسابرسی ثبت شد")

    # شرکت ناشناس نباید درخواست را بشکند، فقط محدودیت محصول برداشته می‌شود
    unknown = await integrations.answer({
        "messages": [{"role": "user", "content": "چطور رمز را عوض کنم؟"}],
        "metadata": {"company": "شرکت ناشناس"},
    }, key="test")
    assert unknown["matched_product"] == "", unknown["matched_product"]
    print("✅ شرکت ناشناس خطا نمی‌دهد و روی همه‌ی محصول‌ها جستجو می‌کند")

    # ورودی‌های بد باید ۴۰۰ بدهند، نه ۵۰۰
    from fastapi import HTTPException
    for bad, label in (
        ({"messages": []}, "messages خالی"),
        ({"messages": [{"role": "assistant", "content": "x"}]}, "آخرین پیام از assistant"),
        ({"messages": "نه آرایه"}, "messages آرایه نیست"),
        ({"messages": [{"role": "user", "content": "x"}], "metadata": "نه شیء"}, "metadata شیء نیست"),
    ):
        try:
            await integrations.answer(bad, key="test")
        except HTTPException as exc:
            assert exc.status_code == 400, f"{label}: {exc.status_code}"
        else:
            print(f"❌ ورودی بد پذیرفته شد: {label}"); passed = False
    print("✅ ورودی‌های نامعتبر با خطای ۴۰۰ رد می‌شوند")

    # کلید نامعتبر نباید بپذیرد
    os.environ["INTEGRATION_API_KEYS"] = ""
    settings.invalidate()
    assert not settings.integration_key_is_valid("anything")
    assert not integrations.is_integration_request("Bearer anything")
    settings.save({"integration_api_keys": "mil_key_one,mil_key_two"})
    assert integrations.is_integration_request("Bearer mil_key_one")
    assert integrations.is_integration_request("Bearer mil_key_two")
    assert not integrations.is_integration_request("Bearer mil_key_thr")
    assert not integrations.is_integration_request("mil_key_one")   # بدون Bearer
    print("✅ فقط کلیدهای ثبت‌شده پذیرفته می‌شوند")

    for doc_id in ids.values():
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    rag.invalidate() if hasattr(rag, "invalidate") else None
    return passed


async def main():
    db.init_db()
    ok = True

    # ---- سند داخلی (SQL) و سند عمومی ----
    internal = str(WORK / 'internal.txt')
    public = str(WORK / 'public.txt')
    open(internal, 'w', encoding='utf-8').write(
        "رمز عبور را فراموش کردم؟\nدستور زیر را در Database اجرا کنید: delete from log1 where kcod=1\n"
        "این روش فقط برای کارشناسان است.\n" * 3
    )
    open(public, 'w', encoding='utf-8').write(
        "چگونه فاکتور برگشت از فروش ثبت کنم؟\nمنوی فروش را باز کنید و گزینه‌ی برگشت از فروش را بزنید.\n"
        "سپس کالا را انتخاب و ذخیره کنید.\n" * 3
    )

    doc_internal = db.execute(
        "INSERT INTO documents(title, filename, path, audience, size_bytes) VALUES (?,?,?,?,?)",
        ("راهنمای داخلی", "internal.txt", internal, "internal", os.path.getsize(internal)))
    doc_public = db.execute(
        "INSERT INTO documents(title, filename, path, audience, size_bytes) VALUES (?,?,?,?,?)",
        ("راهنمای مشتری", "public.txt", public, "public", os.path.getsize(public)))

    r1 = await rag.index_document(doc_internal)
    r2 = await rag.index_document(doc_public)
    print("ایندکس:", r1, r2)
    assert r1["embedded"] and r2["embedded"], "بردارسازی انجام نشد"

    embedded = db.query_one("SELECT COUNT(*) c FROM chunks WHERE embedding IS NOT NULL")["c"]
    print(f"✅ {embedded} تکه بردارگذاری شد ({calls['embed']} فراخوانی embed)")

    # ---- تفکیک دسترسی ----
    public_hits = await rag.search("رمز عبور فراموش کردم", audience="public")
    internal_hits = await rag.search("رمز عبور فراموش کردم", audience="internal")
    leaked = [h for h in public_hits if h.doc_id == doc_internal]
    if leaked:
        print("❌ نشت اطلاعات داخلی به مشتری!"); ok = False
    else:
        print(f"✅ تفکیک دسترسی درست است (مشتری {len(public_hits)} منبع، پشتیبان {len(internal_hits)} منبع)")
    assert any(h.doc_id == doc_internal for h in internal_hits), "پشتیبان سند داخلی را ندید"

    # ---- استریم پاسخ ----
    events = []
    async for raw in chat_service.answer_stream(
        "چطور فاکتور برگشت از فروش ثبت کنم؟",
        session_id="s1", audience="public", client_id="client-a",
    ):
        events.append(json.loads(raw[5:].strip()))
    kinds = [e["type"] for e in events]
    print("رویدادها:", kinds)
    assert kinds[0] == "user", "شناسه‌ی پیام کاربر اول از همه نیامد"
    assert kinds[1] == "sources" and kinds[-1] == "done", "ترتیب رویدادها درست نیست"
    answer = "".join(e["text"] for e in events if e["type"] == "delta")
    assert answer, "متن پاسخ خالی است"
    print(f"✅ استریم کار می‌کند → {answer[:45]}…")

    # ---- ذخیره در دیتابیس ----
    msgs = db.query("SELECT role, content, sources, grounded FROM messages ORDER BY id")
    assert len(msgs) == 2 and msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
    assert json.loads(msgs[1]["sources"]), "منابع ذخیره نشد"
    print(f"✅ گفتگو در دیتابیس ذخیره شد ({len(msgs)} پیام، منابع ثبت شد)")

    # ---- حافظه‌ی گفتگو ----
    async for _ in chat_service.answer_stream(
        "و بعدش؟", session_id="s1", audience="public", client_id="client-a"
    ):
        pass
    total = db.query_one("SELECT COUNT(*) c FROM messages")["c"]
    assert total == 4, f"انتظار ۴ پیام، دریافت {total}"
    convs = db.query_one("SELECT COUNT(*) c FROM conversations")["c"]
    assert convs == 1, "برای یک نشست بیش از یک گفتگو ساخته شد"
    print("✅ حافظه‌ی گفتگو روی یک نشست حفظ شد")

    # ---- جداسازی گفتگوها ----
    # مرورگر دیگری که همان session_id را بداند نباید چیزی ببیند.
    mine = chat_service.conversation_messages("s1", "public", "client-a")
    theirs = chat_service.conversation_messages("s1", "public", "client-b")
    assert len(mine) == 4, f"صاحب گفتگو باید ۴ پیام ببیند، دید {len(mine)}"
    assert theirs == [], "گفتگوی یک نفر به مرورگر دیگری نشان داده شد"
    assert chat_service.conversation_messages("s1", "public", "") == [], \
        "بدون شناسه‌ی معتبر هم گفتگو برگشت"
    # و نباید بتواند گفتگوی او را عقب ببرد یا پاک کند
    first_id = db.query_one("SELECT MIN(id) i FROM messages")["i"]
    assert not chat_service.rewind_to("s1", "public", "client-b", first_id), \
        "مرورگر غریبه توانست گفتگوی دیگری را عقب ببرد"
    assert not chat_service.message_belongs_to(first_id, "client-b"), \
        "بازخورد روی پیام دیگری مجاز شد"
    assert chat_service.message_belongs_to(first_id, "client-a")
    print("✅ هر مرورگر فقط گفتگوی خودش را می‌بیند")

    # ---- منابع فقط برای پشتیبان ----
    assert all(not m["sources"] for m in mine), "منبع به مشتری نشان داده شد"
    stored = db.query_one(
        "SELECT sources FROM messages WHERE role='assistant' ORDER BY id LIMIT 1"
    )["sources"]
    assert json.loads(stored), "منابع باید در دیتابیس بمانند تا پشتیبان ببیند"
    print("✅ منابع از مشتری پنهان است ولی در دیتابیس ثبت می‌شود")

    # ---- ویرایش و ارسال دوباره ----
    last_user = db.query_one(
        "SELECT id FROM messages WHERE role='user' ORDER BY id DESC LIMIT 1"
    )["id"]
    assert chat_service.rewind_to("s1", "public", "client-a", last_user)
    left = chat_service.conversation_messages("s1", "public", "client-a")
    assert len(left) == 2, f"بعد از عقب بردن باید ۲ پیام بماند، ماند {len(left)}"
    print("✅ عقب بردن گفتگو، سوال و پاسخ بعدش را پاک می‌کند")

    # ---- تفکیک محصول‌ها و اندپوینت سامانه‌ی تیکت ----
    ok = await check_integration() and ok

    # ---- بازسازی متن ----
    broken = "چجور ی کاالها ی داخل سرور رو ببر می داخل س ی ستم نت ی کال صندوق سواالت " * 4
    fixed, count = await repair.repair_pages([broken])
    assert count == 1 and "سوالات" in fixed[0], "بازسازی متن شکسته کار نکرد"
    clean = "منوی فروش را باز کنید و گزینه‌ی برگشت از فروش را بزنید. کالا را ذخیره کنید. " * 6
    _, skipped = await repair.repair_pages([clean])
    assert skipped == 0, "متن سالم بی‌دلیل به مدل فرستاده شد"
    print("✅ بازسازی متن فقط روی صفحه‌های شکسته اجرا می‌شود")

    # ---- طول پاسخ: همان سقف برای همه، دستور از پرامپت می‌آید ----
    from app import config as app_config

    markers = {"short": "حالت کوتاه", "normal": "حالت متوسط", "detailed": "حالت کامل"}
    for mode, marker in markers.items():
        seen_prompt = {}

        async def capture(messages, model=None, temperature=0.0, max_tokens=None, meta=None,
                          _seen=seen_prompt):
            _seen["prompt"] = messages[-1]["content"]
            _seen["max_tokens"] = max_tokens
            yield "پاسخ"
            if meta is not None:
                meta["finish_reason"] = "stop"

        chat_service.avalai.chat_stream = capture
        async for _ in chat_service.answer_stream(
            "تست طول", session_id=f"len-{mode}", audience="public", length=mode
        ):
            pass
        assert marker in seen_prompt["prompt"], f"دستور «{marker}» به مدل نرسید"
        assert seen_prompt["max_tokens"] == app_config.ANSWER_MAX_TOKENS, \
            f"سقف توکن برای حالت {mode} فرق دارد — پاسخ ممکن است بریده شود"
    chat_service.avalai.chat_stream = fake_stream
    print(f"✅ هر سه حالت طول یک سقف توکن دارند ({app_config.ANSWER_MAX_TOKENS}) و دستورشان از پرامپت می‌آید")

    # ---- پاسخ نیمه‌کاره باید اعلام شود ----
    async def truncated(messages, model=None, temperature=0.0, max_tokens=None, meta=None):
        yield "جواب ناقصِ ب"
        if meta is not None:
            meta["finish_reason"] = "length"

    chat_service.avalai.chat_stream = truncated
    text = ""
    async for raw in chat_service.answer_stream(
        "تست قطع", session_id="cut", audience="public", length="short"
    ):
        event = json.loads(raw[5:])
        if event["type"] == "delta":
            text += event["text"]
    assert "ناقص ماند" in text, "پاسخ بریده‌شده بی‌صدا رد شد"
    chat_service.avalai.chat_stream = fake_stream
    print("✅ پاسخ بریده‌شده به کاربر اعلام می‌شود")

    # ---- «بازنویسی برای مشتری» نباید نصفه بماند ----
    from app import avalai as app_avalai

    rewrite_seen = {}

    async def rewrite_chat(messages, model=None, temperature=0.0, max_tokens=None, meta=None):
        rewrite_seen["max_tokens"] = max_tokens
        rewrite_seen["system"] = messages[0]["content"]
        if meta is not None:
            meta["finish_reason"] = "length"      # وانمود می‌کنیم به سقف خورده
        return "متن نیمه‌کاره‌ی ب"

    real_chat = app_avalai.chat
    app_avalai.chat = rewrite_chat
    try:
        from app import main as app_main
        response = await app_main.agent_rewrite(
            app_main.RewriteIn(text="یک پاسخ فنی طولانی"), role="agent"
        )
    finally:
        app_avalai.chat = real_chat
        avalai.chat = fake_chat

    assert rewrite_seen["max_tokens"] == app_config.ANSWER_MAX_TOKENS, \
        "بازنویسی برای مشتری سقف توکن جداگانه دارد — پاسخ بریده می‌شود"
    assert "کامل تمام کن" in rewrite_seen["system"], "دستور «کامل تمام کن» در پرامپت بازنویسی نیست"
    assert response["truncated"] and "ناقص ماند" in response["text"], \
        "بازنویسیِ بریده‌شده بی‌صدا رد شد"
    print("✅ «بازنویسی برای مشتری» همان سقف را دارد و اگر ناقص بماند اعلام می‌شود")

    # ---- خواندن تصویری صفحه‌های PDF ----
    guide = next(
        (p for p in Path("docs").glob("*.pdf") if vision.pages_with_images(p)), None
    ) if Path("docs").exists() else None

    if guide:
        vision.config.VISION_MAX_PAGES = 2  # برای سرعت تست
        doc_pdf = db.execute(
            "INSERT INTO documents(title, filename, path, audience, size_bytes) VALUES (?,?,?,?,?)",
            (guide.stem, guide.name, str(guide), "internal", guide.stat().st_size))
        before = calls["vision"]
        info = await rag.index_document(doc_pdf)
        assert info["vision_pages"] == 2, f"انتظار ۲ صفحه‌ی تصویری، دریافت {info['vision_pages']}"
        assert calls["vision"] - before == 2, "مدل بینایی فراخوانی نشد"
        avg_kb = sum(calls["image_bytes"]) // len(calls["image_bytes"]) // 1024
        found = db.query_one("SELECT page FROM chunks WHERE text LIKE '%Welcome%' LIMIT 1")
        assert found, "متنِ آمده از تصویر وارد ایندکس نشد"
        print(f"✅ اسکرین‌شات‌ها خوانده و ایندکس شدند "
              f"({info['vision_pages']} صفحه، میانگین {avg_kb} کیلوبایت، صفحه‌ی {found['page']})")
    else:
        print("• تست بینایی رد شد (فایل PDF عکس‌داری در پوشه‌ی docs نبود)")

    # ---- حذف سند ----
    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_public,))
    db.execute("DELETE FROM documents WHERE id = ?", (doc_public,))
    rag.invalidate_cache()
    remaining = await rag.search("فاکتور برگشت از فروش", audience="public")
    assert not [h for h in remaining if h.doc_id == doc_public], "تکه‌های سند حذف‌شده باقی ماند"
    print("✅ حذف سند، تکه‌هایش را هم پاک می‌کند")

    print("\n" + ("همه‌ی تست‌ها موفق ✅" if ok else "برخی تست‌ها ناموفق ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    raise SystemExit(code)
