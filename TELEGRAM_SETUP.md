# REELS AI FACTORY — TELEGRAM APPROVAL BOT KURULUM KILAVUZU

Bu kılavuz, 6. gün haftalık içerik onaylarını Telegram üzerinden tek tıkla (**[✅ EVET]** / **[❌ HAYIR]**) yönetebilmeniz için gereken Telegram Bot kurulumunu anlatır.

---

### ADIM 1: Telegram'da @BotFather ile Yeni Bot Oluşturun
1. Telegram uygulamanızda **[@BotFather](https://t.me/BotFather)** kullanıcısını açın.
2. `/newbot` komutunu gönderin.
3. Botunuz için bir isim belirleyin (Örn: `Reels AI Factory Control`).
4. Botunuz için `_bot` ile biten benzersiz bir kullanıcı adı belirleyin (Örn: `ReelsAIFactory_bot`).
5. BotFather size bir **HTTP API Token** verecektir (Örn: `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`).

---

### ADIM 2: Token'ı `.env` Dosyasına Ekleyin
Proje ana dizinindeki `.env` dosyasını açın ve token'ı ekleyin:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz
```

---

### ADIM 3: Botunuza `/start` Mesajı Gönderin
1. Telegram'da yeni oluşturduğunuz botu bulun (Örn: `@ReelsAIFactory_bot`).
2. **Başlat** butonuna basın veya `/start` mesajı gönderin.

---

### ADIM 4: Kullanıcı ve Chat ID'nizi Öğrenin
Proje dizininde şu komutu çalıştırarak ID'lerinizi ekranda görün:

```cmd
.venv\Scripts\python.exe -m automation.cloud.telegram_identity_helper
```

Ekranda çıkan ID'leri `.env` dosyanıza yazın:

```env
TELEGRAM_ALLOWED_USER_ID=123456789
TELEGRAM_CHAT_ID=123456789
WEEKLY_APPROVAL_DAY=6
WEEKLY_APPROVAL_LOCAL_TIME=12:00
TELEGRAM_WEBHOOK_SECRET=reels_ai_webhook_secret_2026
```

---

### ADIM 5: Doğrulamayı Çalıştırın
Tüm ayarların hazır olduğunu test etmek için:

```cmd
TELEGRAM_PREFLIGHT.bat
```

Ekranda **`STATUS: TELEGRAM_PREFLIGHT_PASS`** gördüğünüzde Telegram onay altyapınız hazır demektir.
