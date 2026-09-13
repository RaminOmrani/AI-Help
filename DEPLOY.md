# راهنمای انتشار روی `aiassist.softmiliac.com`

این پروژه یک برنامه‌ی پایتون است که باید **همیشه در حال اجرا** بماند
(مثل یک سرویس)، نه مجموعه‌ای از فایل‌های PHP که روی هاست کپی شوند.

> ⚠️ **روی هاست اشتراکی (cPanel / دایرکت‌ادمین) معمولاً کار نمی‌کند.**
> این نوع هاست‌ها اجازه‌ی اجرای پروسه‌ی دائمی نمی‌دهند. اگر سایت اصلی‌تان
> روی هاست اشتراکی است، برای این بخش به یک **سرور مجازی (VPS)** نیاز دارید —
> ارزان‌ترین پلن هم کافی است (۲ گیگ رم).

**حداقل سخت‌افزار:** ۱ هسته CPU، ۲ گیگابایت رم، ۱۰ گیگابایت دیسک.

---

## قدم صفر: DNS

در پنل مدیریت دامنه‌ی `softmiliac.com` یک رکورد اضافه کنید:

| نوع | نام | مقدار |
|---|---|---|
| `A` | `aiassist` | آی‌پی سرور |

اگر از کلادفلر استفاده می‌کنید، فعلاً ابر را **خاکستری** (DNS only) بگذارید تا
گواهی صادر شود؛ بعد می‌توانید نارنجی‌اش کنید.

بررسی کنید که دامنه به **همان سروری** رسیده باشد که می‌خواهید روی آن نصب کنید
(دامنه‌ی اصلی روی cPanel است و آی‌پی دیگری دارد؛ این زیر‌دامنه باید به VPS اشاره کند):

```bash
# روی خود VPS بزنید — دو خروجی باید یکی باشند
curl -s ifconfig.me; echo
getent hosts aiassist.softmiliac.com
```

و مطمئن شوید پورت ۸۰ آزاد است (اگر آپاچی یا سایت دیگری روی همین VPS است، تداخل می‌شود):

```bash
sudo ss -tlnp | grep -E ':80|:443'
```

---

## روش ۱ — سرور لینوکس (پیشنهادی)

فرض: اوبونتو ۲۲.۰۴ یا بالاتر، دسترسی root.

### ۱. پیش‌نیازها

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx
```

### ۲. کاربر و پوشه‌ی سرویس

سرویس با کاربر جداگانه اجرا می‌شود تا اگر مشکلی پیش آمد به بقیه‌ی سرور دست نداشته باشد:

```bash
sudo adduser --system --group --home /opt/aiassist aiassist
sudo -u aiassist git clone -b claude/ai-support-assistant-grtf7b \
    https://github.com/RaminOmrani/AI-Help /opt/aiassist
```

### ۳. نصب وابستگی‌ها

```bash
cd /opt/aiassist
sudo -u aiassist python3 -m venv venv
sudo -u aiassist venv/bin/pip install --upgrade pip
sudo -u aiassist venv/bin/pip install -r requirements.txt
```

### ۴. تنظیمات امن

این دستور رمزهای تصادفی و `SECRET_KEY` می‌سازد و `.env` را برای حالت پشت nginx تنظیم می‌کند:

```bash
sudo -u aiassist venv/bin/python scripts/preflight.py \
    --fix --domain aiassist.softmiliac.com
```

**رمزهایی که چاپ می‌شوند را همان لحظه جایی امن ذخیره کنید** — دیگر نشانشان نمی‌دهد.
اگر جا ماندند، در `.env` هستند:

```bash
grep -E '^(ADMIN_PASSWORD|AGENT_PASSWORD)=' /opt/aiassist/.env
```

**اگر رمز دلخواه خودتان را می‌خواهید** (به‌جای رمز تصادفی)، این را اجرا کنید و رمز را
دو بار تایپ کنید — حروف فارسی هم قبول است:

```bash
sudo -u aiassist python3 scripts/setpass.py
sudo systemctl restart aiassist
```

### ۵. اجرا به‌عنوان سرویس

```bash
sudo cp deploy/aiassist.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiassist
sudo systemctl status aiassist
```

بررسی کنید واقعاً بالا آمده باشد — باید `200` چاپ کند:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/
```

اگر `200` نبود، علتش را اینجا ببینید:

```bash
sudo journalctl -u aiassist -n 50 --no-pager
```

### ۶. nginx و گواهی HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/aiassist
sudo ln -s /etc/nginx/sites-available/aiassist /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

فایل ارسالی عمداً فقط `HTTP` دارد؛ `certbot` خودش بلوک `HTTPS` را اضافه می‌کند.
اگر این VPS سایت دیگری ندارد، صفحه‌ی پیش‌فرض nginx را بردارید تا مزاحم نشود:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

حالا گواهی:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d aiassist.softmiliac.com
```

certbot خودش گواهی می‌گیرد، بلوک HTTPS را کامل می‌کند و تمدید خودکار را تنظیم می‌کند.

### ۷. فایروال

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
```

پورت ۸۰۰۰ را **باز نکنید** — فقط nginx باید به آن دسترسی داشته باشد.

---

## روش ۲ — داکر

اگر نمی‌خواهید پایتون روی سرور نصب کنید:

```bash
git clone -b claude/ai-support-assistant-grtf7b \
    https://github.com/RaminOmrani/AI-Help /opt/aiassist
cd /opt/aiassist
cp .env.example .env
python3 scripts/preflight.py --fix --domain aiassist.softmiliac.com

docker compose -f deploy/docker-compose.yml up -d
```

بعد همان مراحل ۶ و ۷ بالا (nginx و گواهی) را انجام دهید.

---

## روش ۳ — ویندوز سرور

اگر سرورتان ویندوز است:

1. پایتون را نصب کنید (تیک **Add python.exe to PATH**).
2. پروژه را در `C:\aiassist` بگیرید و یک بار `start.bat` را بزنید تا محیط ساخته شود.
3. `python scripts/preflight.py --fix --domain aiassist.softmiliac.com` را اجرا کنید.
4. با [NSSM](https://nssm.cc) برنامه را سرویس ویندوزی کنید تا با ری‌استارت سرور خودکار بالا بیاید:

```bat
nssm install AIAssist C:\aiassist\venv\Scripts\python.exe C:\aiassist\run.py
nssm set AIAssist AppDirectory C:\aiassist
nssm start AIAssist
```

5. در **IIS** یک سایت برای `aiassist.softmiliac.com` بسازید و با
   **Application Request Routing** به `http://127.0.0.1:8000` ریورس‌پروکسی کنید.
   حتماً بافرینگ پاسخ را **خاموش** کنید، وگرنه پاسخ‌ها استریم نمی‌شوند.

---

## بعد از بالا آمدن

### ۱. بررسی نهایی

```bash
cd /opt/aiassist
sudo -u aiassist venv/bin/python scripts/preflight.py
```

باید همه‌ی خط‌ها ✅ باشند.

### ۲. کلید و مستندات

1. به `https://aiassist.softmiliac.com/admin` بروید و با رمز مدیر وارد شوید.
2. تب **«🔑 کلید و مدل‌ها»** → کلید AvalAI را بگذارید → **ذخیره** → **«🔌 تست اتصال»**.
3. تب **«📚 مستندات»** → فایل‌های راهنما را بارگذاری کنید.
4. **سطح دسترسی هر فایل را درست بگذارید** — این مهم‌ترین تنظیم است:

| فایل | مخاطب |
|---|---|
| راهنمای جامع (دارای رمز، SQL، تنظیمات سرور) | **فقط کارشناسان پشتیبانی** |
| راهنمای سریع مشتری | هم مشتری، هم پشتیبان |

اگر فایلی که رمز دارد را روی «هم مشتری» بگذارید، دستیار مشتری هم آن را می‌بیند.

### ۳. لوگو و نام

نام دستیار «میلیونر بات» است و در `.env` با `ASSISTANT_NAME` قابل تغییر است.

نشانی که در هدر و کنار پاسخ‌ها دیده می‌شود از یک فایل می‌آید:

```
/opt/aiassist/web/assets/logo.svg
```

برای گذاشتن لوگوی رسمی کافی است **همین یک فایل** را با نسخه‌ی SVG لوگو عوض کنید
(نیازی به ری‌استارت هم نیست؛ فقط مرورگر را با `Ctrl+Shift+R` تازه کنید).
رنگ نشان از تم گرفته می‌شود، پس لوگو باید تک‌رنگ و تک‌تکه باشد تا در تم تیره هم
خوانا بماند.

### ۴. محدود کردن دسترسی (فعلاً فقط تیم و مشتریان میلیونر)

در همان پنل، تب **«🔑 کلید و مدل‌ها»** → بخش **«دسترسی صفحه‌ی مشتری»**:

| حالت | یعنی |
|---|---|
| **باز** | هر کسی با لینک می‌تواند بپرسد |
| **با کد** | اول باید یک کد دسترسی وارد کند |

فعلاً **«با کد»** را بزنید و چند کد بنویسید (هر کدام در یک خط)، مثلاً یکی برای
تیم پشتیبانی و یکی برای مشتریان. هر وقت خواستید برای همه باز شود، همین‌جا
روی **«باز»** بگذارید — نیازی به دست زدن به سرور نیست.

کد یک بار وارد می‌شود و در مرورگر کاربر می‌ماند؛ با رفرش دوباره پرسیده نمی‌شود.

### ۵. سه آدرس نهایی

| آدرس | برای چه کسی |
|---|---|
| `https://aiassist.softmiliac.com/` | مشتریان — این را می‌توانید از سایت اصلی لینک بدهید |
| `https://aiassist.softmiliac.com/agent` | کارشناسان پشتیبانی (پشت رمز) |
| `https://aiassist.softmiliac.com/admin` | مدیر دانش (پشت رمز) |

---

## محافظت از اعتبار AvalAI

صفحه‌ی مشتری عمومی است، پس سقف پیش‌فرض برای هر آی‌پی گذاشته شده:

```env
RATE_LIMIT_PER_MINUTE=10
RATE_LIMIT_PER_DAY=150
```

این‌ها را در `.env` می‌توانید تغییر دهید. برای اینکه سقف درست کار کند،
`TRUST_PROXY=true` باید روشن باشد (اسکریپت preflight خودش تنظیمش می‌کند) —
وگرنه همه‌ی کاربران از دید برنامه یک نفر دیده می‌شوند.

اعتبار باقی‌مانده را در پنل مدیریت می‌بینید. توصیه: **هفته‌ی اول هر روز نگاهش کنید**
تا بفهمید مصرف واقعی چقدر است.

---

## به‌روزرسانی

```bash
cd /opt/aiassist
sudo -u aiassist git pull
sudo -u aiassist venv/bin/pip install -r requirements.txt
sudo systemctl restart aiassist
```

مستندات و کلید و گفتگوها در پوشه‌ی `data/` می‌مانند و با به‌روزرسانی پاک نمی‌شوند.

---

## پشتیبان‌گیری

همه‌ی داده‌ها در دو جا هستند:

```
/opt/aiassist/data/support.db     دیتابیس: مستندات ایندکس‌شده، گفتگوها، تیکت‌ها، کلید
/opt/aiassist/data/uploads/       فایل‌های اصلیِ بارگذاری‌شده
```

یک بکاپ شبانه:

```bash
sudo crontab -e
# این خط را اضافه کنید:
0 3 * * * tar czf /root/aiassist-$(date +\%F).tar.gz /opt/aiassist/data
```

---

## عیب‌یابی

| نشانه | علت محتمل |
|---|---|
| پاسخ‌ها یکجا می‌آیند، نه کلمه‌به‌کلمه | `proxy_buffering off` در nginx نیست |
| آپلود PDF بزرگ خطای ۴۱۳ می‌دهد | `client_max_body_size` کم است |
| بارگذاری وسط کار قطع می‌شود | `proxy_read_timeout` کم است (باید ۶۰۰s باشد) |
| همه‌ی کاربران سریع به سقف می‌خورند | `TRUST_PROXY=true` نیست |
| «جستجوی معنایی در دسترس نیست» | اتصال سرور به `api.avalai.ir` ناپایدار است |

دیدن لاگ زنده:

```bash
sudo journalctl -u aiassist -f
```
