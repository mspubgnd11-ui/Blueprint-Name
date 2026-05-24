# 🤖 بوت الأرقام الافتراضية

## 📁 الملفات
- `config.py`      — الإعدادات (توكن البوت، API key، IDs الأدمن)
- `database.py`    — قاعدة البيانات SQLite
- `api_client.py`  — التواصل مع موقع الأرقام
- `bot.py`         — البوت الرئيسي

## ⚙️ طريقة التشغيل

### 1. ثبّت المكتبات
```bash
pip install -r requirements.txt
```

### 2. عدّل config.py
```python
BOT_TOKEN    = "توكن البوت من @BotFather"
API_KEY      = "f5b42507-699e-4c7b-83cd-4effad88b932"
API_BASE_URL = "https://رابط-موقع-الأرقام-تبعك"
ADMIN_IDS    = [YOUR_TELEGRAM_ID]
```

### 3. شغّل البوت
```bash
python bot.py
```

## 🔑 أوامر الأدمن
من داخل البوت:
- اضغط **لوحة الأدمن** ← **إضافة رصيد**
- أرسل: `USER_ID المبلغ`  مثال: `123456789 10.00`

## ⚠️ مهم — ربط الـ API
افتح `api_client.py` وعدّل الـ endpoints حسب موقعك.
أرسل رابط موقعك أو الـ docs وأنا أعدّلها عنك.

