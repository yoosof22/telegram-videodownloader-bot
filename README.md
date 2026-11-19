# ربات دانلود ویدیو تلگرام (TikTok / Instagram)

ربات تلگرامی برای دانلود ویدیو از تیک‌تاک و اینستاگرام (Reel، Post، TV) و ارسال مستقیم به کاربر.

## ✨ ویژگی‌ها

- 🎬 دانلود از **TikTok** (tiktok.com، vm.tiktok.com، vt.tiktok.com)
- 📸 دانلود از **Instagram** (Reel، Post، TV)
- ⚡ ارسال ویدیو با پشتیبانی از استریم (`supports_streaming=True`)
- 🔒 پشتیبانی از پروکسی (SOCKS5/HTTP) برای اتصال از ایران
- 🍪 پشتیبانی از کوکی‌های اینستاگرام برای محتوای خصوصی
- ⏱ محدودیت نرخ کاربری و همزمانی سراسری
- 🧹 پاک‌سازی خودکار فایل‌های موقت
- 📝 لاگ‌گیری کامل در کنسول و فایل

## 📋 پیش‌نیازها

- **Python 3.11+**
- **ffmpeg** (باید در PATH سیستم باشد)
- توکن ربات از [@BotFather](https://t.me/BotFather)

### نصب ffmpeg

**Windows:**
```powershell
# با Chocolatey
choco install ffmpeg

# با Scoop
scoop install ffmpeg

# یا دانلود مستقیم از https://ffmpeg.org/download.html
# و اضافه کردن به PATH
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**تست نصب:**
```bash
ffmpeg -version
```

## 🚀 نصب و اجرا

### ۱. کلون و ورود به پوشه
```bash
git clone <repo-url>
cd telegram-video-bot
```

### ۲. محیط مجازی و وابستگی‌ها
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### ۳. تنظیمات
```bash
cp .env.example .env
```

فایل `.env` را باز کنید و مقادیر را پر کنید:

```env
BOT_TOKEN=""
PROXY_URL=socks5://127.0.0.1:1080    # اگر در ایران هستید
INSTAGRAM_COOKIES=./cookies.txt      # اختیاری
MAX_FILE_MB=50
RATE_LIMIT_PER_MIN=5
```

### ۴. اجرا
```bash
python bot.py
```

## 🐳 اجرا با Docker

### Dockerfile
```dockerfile
FROM python:3.11-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "bot.py"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: tg-video-bot
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./downloads:/app/downloads
      - ./cookies.txt:/app/cookies.txt:ro
```

اجرای با Docker:
```bash
docker-compose up -d
# لاگ‌ها:
docker-compose logs -f
```

## ⚙️ تنظیمات (Environment Variables)

| متغیر | پیش‌فرض | توضیح |
|--------|---------|-------|
| `BOT_TOKEN` | **الزامی** | توکن ربات از @BotFather |
| `PROXY_URL` | خالی | پروکسی برای تلگرام و yt-dlp (مثال: `socks5://127.0.0.1:1080`) |
| `INSTAGRAM_COOKIES` | خالی | مسیر فایل cookies.txt برای اینستاگرام |
| `MAX_FILE_MB` | 50 | حداکثر حجم فایل دانلود (مگابایت) |
| `RATE_LIMIT_PER_MIN` | 5 | حداکثر درخواست هر کاربر در دقیقه |

## 🍪 دریافت کوکی‌های اینستاگرام (اختیاری)

برای دانلود محتوای خصوصی یا محدود شده:

1. افزونه **EditThisCookie** یا **Get cookies.txt LOCALLY** را در مرورگر نصب کنید
2. در سایت instagram.com لاگین کنید
3. کوکی‌ها را به فرمت **Netscape** صادرات کنید
4. فایل را به نام `cookies.txt` در ریشه پروژه ذخیره کنید
5. در `.env` مسیر را تنظیم کنید: `INSTAGRAM_COOKIES=./cookies.txt`

## 🔄 به‌روزرسانی yt-dlp

yt-dlp به‌صورت مداوم به‌روزرسانی می‌شود (سایت‌ها API را تغییر می‌دهند). برای به‌روزرسانی:

```bash
# در محیط مجازی فعال:
pip install -U yt-dlp

# یا در Docker:
docker-compose build --no-cache
docker-compose up -d
```

**پیشنهاد:** یک cronjob هفتگی برای به‌روزرسانی خودکار تنظیم کنید.

## 📁 ساختار پروژه

```
telegram-video-bot/
├── bot.py              # Entry point، هندلرها
├── downloader.py       # منطق دانلود با yt-dlp
├── config.py           # بارگذاری تنظیمات از .env
├── utils.py            # Regex، Rate Limiter، Helpers
├── requirements.txt    # وابستگی‌ها (نسخه‌های پین‌شده)
├── .env.example        # نمونه فایل تنظیمات
├── .gitignore          # فایل‌های نادیده‌گرفته شده
├── Dockerfile          # ایمیج داکر
├── docker-compose.yml  #-compose برای اجرا
├── bot.service         # سرویس systemd
├── README.md           # این فایل
└── bot.log             # لاگ‌های اجرا (تولید خودکار)
```

## 🛠 systemd Service (Linux)

فایل `bot.service` را کپی کنید:
```bash
sudo cp bot.service /etc/systemd/system/tg-video-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now tg-video-bot
```

محتویات `bot.service`:
```ini
[Unit]
Description=Telegram Video Downloader Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/telegram-video-bot
EnvironmentFile=/path/to/telegram-video-bot/.env
ExecStart=/path/to/telegram-video-bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 📖 دستورات ربات

| دستور | توضیح |
|---------|-------|
| `/start` | پیام خوش‌آمدگویی و راهنمای کوتاه |
| `/help` | راهنمای کامل استفاده |

## ⚠️ محدودیت‌ها و عیب‌یابی

### خطاهای رایج:

| خطا | دلیل | راه‌حل |
|------|------|--------|
| `Login required` | پست خصوصی/محدود | کوکی اینستاگرام اضافه کنید |
| `Video unavailable` | ویدیو حذف شده/منقضی | لینک دیگر امتحان کنید |
| `File too large` | > 50MB | کیفیت پایین‌تر دانلود می‌شود |
| `Rate limit` | درخواست‌های زیاد | صبر کنید (پیش‌فرض ۵/دقیقه) |
| `Proxy error` | پروکسی کار نمی‌کند | پروکسی را چک/تغییر دهید |

### لاگ‌ها:
```bash
# کنسول
tail -f bot.log

# systemd
journalctl -u tg-video-bot -f
```

## 📄 مجوز

MIT License - آزاد برای استفاده، تغییر و توزیع.

---

**نکته:** این ربات فقط برای استفاده شخصی/آموزشی است. از قوانین پلتفرم‌ها و کپی‌رایت محتوا رعایت کنید.