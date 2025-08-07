# 🤖 Master Bot - سیستم فروش ربات VPN

سیستم هوشمند برای فروش و مدیریت رباتهای VPN که به صورت خودکار ربات مشتریان را راه‌اندازی می‌کند.

## ✨ ویژگی‌های کلیدی

### 🚀 فروش خودکار
- دریافت توکن ربات و اطلاعات مشتری
- پردازش پرداخت آنلاین (زرین‌پال، آیدی‌پی)
- راه‌اندازی خودکار ربات در کمتر از 5 دقیقه
- ارسال اطلاعات دسترسی به مشتری

### 💰 مدیریت مالی
- سیستم پرداخت آنلاین امن
- مدیریت اشتراک ماهانه/سالانه
- ردیابی پرداخت‌ها و درآمد
- گزارش‌گیری مالی

### 🐳 Deploy خودکار
- استفاده از Docker برای ایزوله‌سازی
- مدیریت منابع سرور
- monitoring وضعیت رباتها
- بکاپ خودکار

## 📋 پیش‌نیازها

### سیستم
- Ubuntu 20.04+ یا CentOS 8+
- Python 3.11+
- Docker & Docker Compose
- حداقل 2GB RAM
- حداقل 20GB فضای دیسک

### خدمات خارجی
- توکن ربات از @BotFather
- حساب زرین‌پال یا آیدی‌پی
- دامنه یا IP عمومی

## 🚀 نصب و راه‌اندازی

### 1. کلون پروژه
```bash
git clone https://github.com/your-repo/master-bot.git
cd master-bot
```

### 2. نصب وابستگی‌ها
```bash
# نصب Python dependencies
pip install -r requirements.txt

# نصب Docker (اگر نصب نیست)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### 3. تنظیمات
```bash
# کپی فایل تنظیمات
cp .env.example .env

# ویرایش تنظیمات
nano .env
```

### 4. راه‌اندازی روش‌های پرداخت
```bash
# اجرای اسکریپت تنظیمات اولیه
python setup_payment_methods.py
```

### 5. ساخت Docker Image برای VPN Bot
```bash
# ساخت image از ربات VPN
docker build -f ../Dockerfile.vpn-bot -t vpn-bot:latest ..
```

### 6. اجرای Master Bot
```bash
python master_bot.py
```

## ⚙️ پیکربندی

### فایل .env
```env
# Bot Configuration
MASTER_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
MASTER_ADMIN_ID=123456789

# Payment Methods
AQAY_API_KEY=your-aqay-api-key
CARD_TO_CARD_ENABLED=true
CRYPTO_ENABLED=true
DEFAULT_DOLLAR_PRICE=52000

# Pricing (تومان)
MONTHLY_PRICE=200000
YEARLY_PRICE=2000000

# Server Configuration
SERVER_HOST=your-domain.com
```

### تنظیم روش‌های پرداخت

#### 🌐 درگاه آقای پرداخت
1. ثبت نام در [aqayepardakht.ir](https://aqayepardakht.ir)
2. دریافت API Key
3. وارد کردن در `.env`:
```env
AQAY_API_KEY=your-api-key
AQAY_ENABLED=true
```

#### 💳 کارت به کارت
1. فعال‌سازی در `.env`:
```env
CARD_TO_CARD_ENABLED=true
```
2. اضافه کردن کارت‌ها از طریق پنل ادمین یا setup script

#### 🪙 رمز ارز
1. فعال‌سازی در `.env`:
```env
CRYPTO_ENABLED=true
DEFAULT_DOLLAR_PRICE=52000
```
2. اضافه کردن کیف پول‌ها از طریق پنل ادمین

## 📊 نحوه استفاده

### برای مشتریان
1. شروع با `/start`
2. مشاهده قیمت‌ها
3. انتخاب پلن (ماهانه/سالانه)
4. وارد کردن توکن ربات
5. وارد کردن آیدی ادمین
6. تنظیم کانال اجباری (اختیاری)
7. پرداخت آنلاین
8. دریافت لینک ربات

### برای مدیر (دستور `/admin`)
- 📊 مشاهده آمار فروش و درآمد
- 💳 مدیریت کارت‌های بانکی
- 🪙 مدیریت کیف پول‌های رمز ارز
- 💵 تنظیم قیمت دلار
- ✅ تایید پرداخت‌های دستی
- 👥 مدیریت مشتریان
- ⚙️ تنظیمات سیستم

## 🏗️ معماری سیستم

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Master Bot    │────│  Payment Gateway │────│    Database     │
│                 │    │ (ZarinPal/IDPay) │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                                               │
         └───────────────────┐                         │
                             │                         │
              ┌──────────────▼──────────────┐         │
              │        Docker Engine        │         │
              └─────────────────────────────┘         │
                             │                         │
    ┌────────────────────────┼────────────────────────┘
    │                        │
┌───▼────┐              ┌───▼────┐              ┌───▼────┐
│Customer│              │Customer│              │Customer│
│ Bot #1 │              │ Bot #2 │              │ Bot #3 │
└────────┘              └────────┘              └────────┘
```

## 💰 مدل کسب‌وکار

### پکیج‌های پیشنهادی
- **ماهانه**: 200,000 تومان
- **سالانه**: 2,000,000 تومان (تخفیف 17%)

### درآمد محتمل
```
10 مشتری ماهانه = 2,000,000 تومان/ماه
50 مشتری ماهانه = 10,000,000 تومان/ماه
100 مشتری ماهانه = 20,000,000 تومان/ماه
```

## 🔧 مشکلات رایج

### ربات پاسخ نمی‌دهد
```bash
# بررسی لاگ‌ها
tail -f master_bot.log

# بررسی وضعیت Docker
docker ps

# ریستارت سرویس
systemctl restart master-bot
```

### خطای پرداخت
- بررسی اعتبار Merchant ID/API Key
- بررسی اتصال اینترنت
- بررسی لاگ‌های payment gateway

### مشکل Deploy
- بررسی Docker service
- بررسی فضای دیسک
- بررسی port های در دسترس

## 📈 بهینه‌سازی عملکرد

### برای تعداد زیاد مشتری
1. استفاده از PostgreSQL به جای SQLite
2. اضافه کردن Redis برای cache
3. Load balancer برای چندین سرور
4. CDN برای فایل‌های استاتیک

### امنیت
1. Firewall configuration
2. SSL certificate
3. Regular backups
4. Monitoring & alerting

## 🔒 امنیت

### نکات مهم
- تغییر پسوردهای پیش‌فرض
- استفاده از HTTPS
- بکاپ منظم دیتابیس
- محدودیت دسترسی SSH

### بکاپ‌گیری
```bash
# بکاپ دیتابیس
cp master_bot.db backup/master_bot_$(date +%Y%m%d).db

# بکاپ کانتینرها
docker save vpn-bot:latest > vpn-bot-backup.tar
```

## 🆘 پشتیبانی

### لاگ‌ها
```bash
# لاگ Master Bot
tail -f master_bot.log

# لاگ کانتینر خاص
docker logs container-name

# لاگ سیستم
journalctl -u master-bot
```

### مانیتورینگ
```bash
# وضعیت کانتینرها
docker ps

# استفاده منابع
docker stats

# فضای دیسک
df -h
```

## 🚀 توسعه

### اضافه کردن ویژگی جدید
1. Fork کردن repository
2. ایجاد branch جدید
3. پیاده‌سازی ویژگی
4. تست کامل
5. ارسال Pull Request

### API Documentation
- `/health` - بررسی وضعیت سیستم
- `/stats` - آمار کلی
- `/customers` - لیست مشتریان

## 📞 تماس

- **Telegram**: @YourSupportBot
- **Email**: support@yourdomain.com
- **GitHub**: [Issues](https://github.com/your-repo/issues)

## 📄 لایسنس

این پروژه تحت لایسنس MIT منتشر شده است.

---

**⚠️ هشدار**: این سیستم برای استفاده تجاری طراحی شده است. لطفاً از قوانین محلی پیروی کنید.