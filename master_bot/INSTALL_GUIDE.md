# 🚀 راهنمای نصب Master Bot

## 📋 پیش‌نیازها

### سیستم عامل
- Ubuntu 20.04+ یا CentOS 7+
- Python 3.8+
- حداقل 2GB RAM
- حداقل 10GB فضای خالی

### نرم‌افزارهای مورد نیاز
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip git docker.io

# CentOS/RHEL
sudo yum update
sudo yum install python3 python3-pip git docker
```

## 📁 مرحله 1: آماده‌سازی فایل‌ها

### ایجاد پوشه پروژه
```bash
mkdir /opt/master_bot
cd /opt/master_bot
```

### کپی فایل‌ها
فایل‌های زیر را در پوشه `/opt/master_bot` قرار دهید:

```
master_bot/
├── start_master_bot.py
├── install.sh
├── test_system.py
├── requirements.txt
├── .env.example
├── README.md
├── master_bot.py
├── database.py
├── payment.py
├── deployment.py
├── discount.py
├── referral_system.py
├── trial_system.py
├── renewal_system.py
├── admin.py
├── config.py
└── setup_payment_methods.py
```

## 🔧 مرحله 2: نصب خودکار

```bash
chmod +x install.sh
./install.sh
```

اسکریپت نصب این کارها رو انجام می‌ده:
- ✅ چک کردن Python و pip
- ✅ نصب وابستگی‌ها
- ✅ ساخت فایل .env
- ✅ چک کردن Docker
- ✅ ساخت service file

## ⚙️ مرحله 3: تنظیم .env

فایل `.env` رو ویرایش کنید:

```bash
nano .env
```

**مهم‌ترین تنظیمات:**
```bash
# اطلاعات ربات (ضروری)
MASTER_BOT_TOKEN=1234567890:ABCDEFghijklmnopQRSTUVwxyz
MASTER_ADMIN_ID=123456789
MASTER_DB_NAME=master_bot.db

# تنظیمات پرداخت
AQAY_API_KEY=your_aqay_api_key
AQAY_BASE_URL=https://api.aqay.ir
AQAY_ENABLED=true
CARD_TO_CARD_ENABLED=true
CRYPTO_ENABLED=true
DEFAULT_DOLLAR_PRICE=70000

# تست رایگان
TRIAL_ENABLED=true
TRIAL_DAYS=3
TRIAL_TRAFFIC_LIMIT_GB=10

# سیستم ارجاع
REFERRER_PERCENTAGE=15
REFEREE_DISCOUNT_PERCENTAGE=10
MIN_PAYOUT_AMOUNT=50000
```

## 🧪 مرحله 4: تست سیستم

```bash
python3 test_system.py
```

اگه همه چیز درست باشه، باید این خروجی رو ببینی:
```
🧪 Master Bot System Test
========================================
🔍 Testing imports...
✅ config module imported
✅ database module imported
...
🏁 Test Results: 7/7 tests passed
🎉 All tests passed! System is ready.
```

## 🚀 مرحله 5: راه‌اندازی

### راه‌اندازی دستی (برای تست)
```bash
python3 start_master_bot.py
```

### راه‌اندازی به عنوان سرویس
```bash
# کپی فایل سرویس
sudo cp master-bot.service /etc/systemd/system/

# فعال‌سازی سرویس
sudo systemctl daemon-reload
sudo systemctl enable master-bot
sudo systemctl start master-bot

# چک کردن وضعیت
sudo systemctl status master-bot
```

## 📊 مرحله 6: راه‌اندازی اولیه

### 1. تنظیم روش‌های پرداخت
```bash
python3 setup_payment_methods.py
```

### 2. تست ربات
- به ربات خود در تلگرام پیام `/start` بفرستید
- باید منوی اصلی نمایش داده شود

### 3. ورود به پنل ادمین
- دستور `/admin` را ارسال کنید
- تنظیمات پرداخت و سیستم را بررسی کنید

## 🔍 عیب‌یابی

### مشکلات رایج

#### 1. خطای Import
```bash
# نصب مجدد وابستگی‌ها
pip3 install --upgrade -r requirements.txt
```

#### 2. خطای Database
```bash
# حذف دیتابیس و ساخت مجدد
rm master_bot.db
python3 start_master_bot.py
```

#### 3. خطای Docker
```bash
# اضافه کردن کاربر به گروه docker
sudo usermod -aG docker $USER
# logout و login مجدد
```

#### 4. مشکل دسترسی فایل
```bash
# تنظیم مجوزها
chmod +x *.py
chmod 644 *.txt *.md
```

### بررسی لاگ‌ها
```bash
# لاگ سرویس
sudo journalctl -u master-bot -f

# لاگ فایل
tail -f master_bot.log
```

## 📱 تست عملکرد

### 1. تست خرید ربات
- `/start` → `💰 خرید ربات`
- وارد کردن اطلاعات ربات
- تست پرداخت

### 2. تست کد تخفیف
- در مرحله پرداخت `🎁 کد تخفیف دارم`
- کد تست: `WELCOME20`

### 3. تست تست رایگان
- `/start` → `🆓 تست رایگان`

### 4. تست پنل ادمین
- `/admin`
- بررسی آمار و تنظیمات

## 🔄 آپدیت سیستم

### آپدیت کد
```bash
# بک‌آپ
cp -r /opt/master_bot /opt/master_bot_backup_$(date +%Y%m%d)

# آپدیت فایل‌ها
# کپی فایل‌های جدید

# ری‌استارت سرویس
sudo systemctl restart master-bot
```

### آپدیت دیتابیس
```bash
# بک‌آپ دیتابیس
cp master_bot.db master_bot_backup_$(date +%Y%m%d).db

# اجرای مایگریشن (در صورت نیاز)
python3 -c "from database import master_db; print('Database updated')"
```

## 🛡️ امنیت

### تنظیمات فایروال
```bash
# باز کردن پورت‌های مورد نیاز
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### بک‌آپ خودکار
```bash
# اضافه کردن به crontab
crontab -e

# بک‌آپ روزانه ساعت 2 شب
0 2 * * * cp /opt/master_bot/master_bot.db /opt/backups/master_bot_$(date +\%Y\%m\%d).db
```

## 📞 پشتیبانی

در صورت بروز مشکل:

1. **چک کردن لاگ‌ها**
2. **اجرای تست سیستم**
3. **بررسی تنظیمات .env**
4. **ری‌استارت سرویس**

### اطلاعات مفید برای عیب‌یابی
```bash
# ورژن Python
python3 --version

# وضعیت سرویس
sudo systemctl status master-bot

# استفاده از منابع
top
df -h

# اتصال به اینترنت
ping google.com
```

---

## ✅ چک‌لیست نصب

- [ ] Python 3.8+ نصب شده
- [ ] فایل‌ها کپی شده
- [ ] وابستگی‌ها نصب شده  
- [ ] فایل .env تنظیم شده
- [ ] تست سیستم موفق
- [ ] سرویس راه‌اندازی شده
- [ ] ربات پاسخ می‌دهد
- [ ] پنل ادمین کار می‌کند
- [ ] پرداخت تست شده

🎉 **تبریک! Master Bot شما آماده است!**