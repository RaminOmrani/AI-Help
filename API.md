# اتصال سامانه‌های داخلی (سرور به سرور)

این مسیر برای سامانه‌هایی است که خودشان با سرور حرف می‌زنند — مثل سامانه‌ی تیکت.
مرورگر کاربر دخالتی ندارد، پس نه کوکی لازم است نه CORS.

---

## آدرس

```
POST https://aiassist.softmiliac.com/api/chat
```

همان مسیرِ صفحه‌ی مشتری است. از روی هدر `Authorization` تشخیص داده می‌شود که
درخواست از یک سامانه‌ی داخلی آمده، نه از مرورگر؛ آن وقت به‌جای پاسخ استریمی،
یک JSON یک‌جا برمی‌گردد.

## هدرها

```
Authorization: Bearer <کلید>
Content-Type: application/json
```

## بدنه

```json
{
  "messages": [
    { "role": "user",      "content": "سلام، فاکتور برگشتی ثبت نمی‌شود" },
    { "role": "assistant", "content": "سلام، از کدام نسخه استفاده می‌کنید؟" },
    { "role": "user",      "content": "نسخه‌ی فروشگاهی" }
  ],
  "metadata": {
    "company": "میلیونر",
    "company_slug": "milionar",
    "department": "پشتیبانی فنی",
    "user_name": "رضا محمدی"
  }
}
```

| فیلد | اجباری | توضیح |
|---|---|---|
| `messages` | ✅ | سابقه‌ی گفتگو به ترتیب زمانی. **آخرین پیام باید `user` باشد.** فقط ۶ پیام آخر به مدل داده می‌شود. |
| `metadata.company` | — | نام نمایشی محصول |
| `metadata.company_slug` | — | اسلاگ محصول؛ اگر بیاید به آن اولویت داده می‌شود چون دقیق‌تر است |
| `metadata.department` | — | فقط به‌عنوان توضیح به مدل داده و در لاگ ثبت می‌شود |
| `metadata.user_name` | — | نام کاربر، برای اینکه پاسخ شخصی‌تر باشد |

### محصول‌های شناخته‌شده

| محصول | `company_slug` |
|---|---|
| میلیونر | `milionar` |
| CRM میلیونر | `milionar-crm` |
| منوکلاب | `menuclub` |
| شاپ مجهز | `shop-mojahaz` |

نام‌های مستعار هم پذیرفته می‌شوند (مثلاً «منو کلاب»، `menu-club`، `CRM`).
اگر هیچ‌کدام نخورد، درخواست رد نمی‌شود ولی جستجو روی **همه‌ی** محصول‌ها انجام
می‌شود و در پاسخ `matched_product` خالی برمی‌گردد — یعنی جای بررسی دارد.

## پاسخ

```json
{
  "reply": "برای ثبت فاکتور برگشت از فروش:\n۱. منوی فروش را باز کنید…",
  "matched_product": "milionar",
  "grounded": true,
  "truncated": false,
  "latency_ms": 2840
}
```

فقط `reply` لازم است؛ بقیه کمکی‌اند و می‌توانید نادیده‌شان بگیرید.

| فیلد | یعنی |
|---|---|
| `matched_product` | محصولی که تشخیص داده شد. خالی = شناخته نشد |
| `grounded` | `false` یعنی در راهنماها چیزی پیدا نشد و پاسخ عمومی است — بهتر است قبل از ارسال به مشتری، کارشناس ببیندش |
| `truncated` | `true` یعنی پاسخ به سقف طول خورده و ممکن است ناقص باشد |

## خطاها

| کد | یعنی |
|---|---|
| `400` | بدنه ایراد دارد — متن `detail` دقیقاً می‌گوید کجا |
| `401` | کلید نیامده یا معتبر نیست |
| `429` | از سقف درخواست رد شده‌اید؛ هدر `Retry-After` می‌گوید چقدر صبر کنید |
| `502` | اتصال به AvalAI برقرار نشد یا مدل خطا داد |
| `503` | کلید AvalAI روی سرور ثبت نشده است |

همه‌ی خطاها به شکل `{"detail": "..."}` و با پیام فارسی برمی‌گردند.

---

## لحن پاسخ — مهم

پاسخ به‌صورت پیش‌فرض **برای مشتری** نوشته می‌شود، چون جواب تیکت در نهایت به
دست مشتری می‌رسد. یعنی همان خط قرمزهای صفحه‌ی مشتری برقرار است: هیچ دستور
SQL، رمز، مسیر فایل سرور یا ارجاع به نام و صفحه‌ی مستندات داخلی در آن نمی‌آید.

اگر سامانه‌ای عمداً پاسخ فنیِ کارشناس‌پسند بخواهد (مثلاً برای نمایش به خودِ
کارشناس در پنل داخلی)، می‌تواند این را در metadata بفرستد:

```json
"metadata": { "audience": "internal" }
```

⚠️ خروجی این حالت **نباید** مستقیم برای مشتری فرستاده شود.

---

## سقف درخواست

شمارش روی خودِ کلید انجام می‌شود، نه آی‌پی — چون همه‌ی درخواست‌ها از یک سرور
می‌آیند. پیش‌فرض‌ها در `.env`:

```env
INTEGRATION_RATE_PER_MINUTE=60
INTEGRATION_RATE_PER_DAY=3000
```

---

## مدیریت کلید

کلیدها در `.env` نگه داشته می‌شوند. چند کلید را با کاما جدا کنید تا هر سامانه
کلید خودش را داشته باشد و بشود یکی را بدون قطع کردن بقیه باطل کرد:

```env
INTEGRATION_API_KEYS=mil_کلید-سامانه-تیکت,mil_کلید-سامانه-دیگر
```

ساخت کلید تازه:

```bash
python3 -c "import secrets; print('mil_' + secrets.token_urlsafe(32))"
```

بعد از تغییر `.env`:

```bash
sudo systemctl restart aiassist
```

**اگر `INTEGRATION_API_KEYS` خالی باشد، این مسیر کاملاً بسته است** و هر
درخواستی ۴۰۱ می‌گیرد.

---

## آماده‌سازی مستندات

این بخش را فراموش نکنید، وگرنه پاسخ‌ها بی‌ربط می‌شوند:

در پنل مدیریت → تب **مستندات** → ستون **محصول** را برای هر فایل درست بگذارید.

- فایل مخصوص یک محصول → همان محصول را انتخاب کنید.
- فایل مشترک (مثل راهنمای نصب یا تغییر رمز) → روی **«همه‌ی محصولات»** بگذارید
  تا برای هر چهار محصول دیده شود.

سوالی که با `company_slug = menuclub` بیاید فقط در فایل‌های منوکلاب و فایل‌های
مشترک جستجو می‌شود؛ راهنمای حسابداری اصلاً دیده نمی‌شود.

---

## نمونه‌ی PHP

```php
$ch = curl_init('https://aiassist.softmiliac.com/api/chat');
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 120,   // مدل گاهی چند ده ثانیه فکر می‌کند
    CURLOPT_HTTPHEADER     => [
        'Authorization: Bearer ' . AIASSIST_KEY,
        'Content-Type: application/json',
    ],
    CURLOPT_POSTFIELDS => json_encode([
        'messages' => [
            ['role' => 'user', 'content' => $ticketText],
        ],
        'metadata' => [
            'company'      => $ticket->company_name,
            'company_slug' => $ticket->company_slug,
            'department'   => $ticket->department,
            'user_name'    => $ticket->user_name,
        ],
    ], JSON_UNESCAPED_UNICODE),
]);

$raw    = curl_exec($ch);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$data = json_decode($raw, true);
if ($status === 200) {
    $suggestion = $data['reply'];
} else {
    error_log('aiassist: ' . ($data['detail'] ?? $raw));
}
```

⏱ **تایم‌اوت را دست‌کم ۱۲۰ ثانیه بگذارید.** پاسخ استریم نمی‌شود، پس تا وقتی
مدل کارش تمام نشود چیزی برنمی‌گردد.

## نمونه‌ی curl

```bash
curl -X POST https://aiassist.softmiliac.com/api/chat \
  -H "Authorization: Bearer $AIASSIST_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role":"user","content":"چطور منوی دیجیتال بسازم؟"}],
    "metadata": {"company":"منوکلاب","company_slug":"menuclub","department":"پشتیبانی فنی"}
  }'
```

---

## سابقه و حسابرسی

هر تماس در جدول `integration_calls` ثبت می‌شود: شرکت، محصول، دپارتمان، نام
کاربر، سوال، پاسخ، اینکه از مستندات درآمده یا نه، و زمان پاسخ‌دهی.

```bash
sqlite3 /opt/aiassist/data/support.db \
  "SELECT created_at, company, product, grounded, substr(question,1,50) FROM integration_calls ORDER BY id DESC LIMIT 20;"
```

برای پیدا کردن سوال‌هایی که مستندات جوابشان را نداشته‌اند:

```bash
sqlite3 /opt/aiassist/data/support.db \
  "SELECT product, question FROM integration_calls WHERE grounded = 0 ORDER BY id DESC LIMIT 30;"
```

این فهرست بهترین راهنما برای اینکه بفهمید چه راهنمایی کم دارید.
