# REELS AI FACTORY — RAILWAY PRODUCTION DEPLOYMENT GUIDE

Bu kılavuz, Reels AI Factory Cloud Control Plane sistemini **Railway** üzerinde tek bir proje içinde (FastAPI + PostgreSQL + Private Storage Bucket) sıfırdan canlıya alma adımlarını içerir.

---

### ADIM 1: Railway Hesabı
1. [railway.com](https://railway.com) adresine gidin ve GitHub hesabınızla giriş yapın.

---

### ADIM 2: Yeni Proje Oluşturun
1. Railway Dashboard'da **"New Project"** butonuna tıklayın.

---

### ADIM 3: GitHub Deponuzu Deploy Edin
1. **"Deploy from GitHub repo"** seçeneğini seçin.
2. `Otomasyon_3` projenizin bulunduğu depoyu seçin.
3. Railway, kök dizindeki `Dockerfile` ve `railway.toml` dosyalarını otomatik olarak tanıyacaktır.

---

### ADIM 4: PostgreSQL Servisini Ekleyin
1. Proje tuvalinde (Canvas) sağ tıklayın veya **"+ Create"** butonuna basın.
2. **"Database"** -> **"Add PostgreSQL"** seçeneğini seçin.

---

### ADIM 5: Private Storage Bucket Ekleyin
1. Proje tuvalinde **"+ Create"** butonuna basın.
2. **"Storage Bucket"** (S3-Compatible) servisini ekleyin.
3. Bucket ayarlarından **Public Access = OFF (Private)** olduğundan emin olun.

---

### ADIM 6: Uygulama Değişkenlerini (Variables) Açın
1. Deponuzdan deploy edilen **Cloud API** servisine tıklayın.
2. **"Variables"** sekmesini açın.

---

### ADIM 7: PostgreSQL Bağlantısını Yapılandırın
1. Variables içine yeni bir değişken ekleyin:
   ```env
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```
   *(Railway bu referansı otomatik olarak canlı PostgreSQL adresinize bağlar).*

---

### ADIM 8: Storage Bucket Değişkenlerini Eşleyin
Bucket Credentials sekmesindeki değerleri uygulamanıza ekleyin:
```env
MEDIA_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=<Bucket_Endpoint_URL>
S3_BUCKET=<Bucket_Name>
S3_ACCESS_KEY_ID=<Bucket_Access_Key>
S3_SECRET_ACCESS_KEY=<Bucket_Secret_Key>
S3_REGION=us-east-1
MEDIA_RETENTION_DAYS=7
ENABLE_MEDIA_CLEANUP=false
```

---

### ADIM 9: Telegram, Meta ve Güvenlik Değişkenlerini Girin
```env
APP_ENV=production
APP_TIMEZONE=Europe/Istanbul

TELEGRAM_BOT_TOKEN=<Telegram_Bot_Token>
TELEGRAM_ALLOWED_USER_ID=1835798213
TELEGRAM_CHAT_ID=1835798213
TELEGRAM_WEBHOOK_SECRET=<Secure_Random_Secret>

WEEKLY_APPROVAL_DAY=6
WEEKLY_APPROVAL_LOCAL_TIME=18:00

META_GRAPH_VERSION=v26.0
META_ACCESS_TOKEN=<Meta_Long_Lived_Access_Token>
INSTAGRAM_ACCOUNT_ID=17841411536006797
INSTAGRAM_EXPECTED_USERNAME=builddverse
INSTAGRAM_PREPARE_MINUTES_BEFORE=15

LOCAL_WORKER_API_KEY=<Secure_Worker_Key>

ENABLE_TELEGRAM_WEBHOOK=true
ENABLE_WEEKLY_SCHEDULER=true
ENABLE_INSTAGRAM_WORKER=true
```

*(Not: `TELEGRAM_WEBHOOK_SECRET` üretmek için yerel terminalde `.venv\Scripts\python.exe -m automation.cloud.generate_webhook_secret` çalıştırabilirsiniz).*

---

### ADIM 10: Public Domain Üretin
1. Cloud API servisinizin **"Settings"** sekmesine gidin.
2. **"Networking"** -> **"Generate Domain"** butonuna tıklayın.
3. Size özel bir URL üretilecektir (Örn: `https://reels-cloud-production.up.railway.app`).

---

### ADIM 11: PUBLIC_BASE_URL Tanımlayın
1. Üretilen HTTPS domain adresini Variables içine ekleyin:
   ```env
   PUBLIC_BASE_URL=https://reels-cloud-production.up.railway.app
   ```
2. Servis otomatik olarak yeniden deploy olacaktır.

---

### ADIM 12: Sağlık Kontrolünü Doğrulayın
1. Tarayıcınızda `https://<DOMAIN>/health` adresini açın.
2. Şu çıktıyı doğrulayın:
   ```json
   {
     "status": "HEALTHY",
     "database": "CONNECTED",
     "scheduler": "ENABLED",
     "telegram_configured": true,
     "instagram_worker": "ENABLED",
     "storage_configured": true
   }
   ```

---

### ADIM 13: Telegram Webhook Planını İnceleyin
Yerel bilgisayarınızda planı görmek için:
```cmd
.venv\Scripts\python.exe -m automation.cloud.setup_telegram_webhook
```

---

### ADIM 14: Telegram Webhook'unu Canlıya Alın
```cmd
.venv\Scripts\python.exe -m automation.cloud.setup_telegram_webhook --apply
```

---

### ADIM 15: Telegram Bağlantı Testi (Smoke Test)
Botunuzun çalıştığını doğrulamak için canlı test mesajı gönderin:
```cmd
.venv\Scripts\python.exe -m automation.cloud.telegram_live_smoke_test --send
```

---

### ADIM 16: Yerel Bilgisayar `.env` Dosyasını Güncelleyin
Yerel `.env` dosyanıza Railway Cloud ve Bucket bilgilerini ekleyin:
```env
PUBLIC_BASE_URL=https://<DOMAIN>
LOCAL_WORKER_API_KEY=<Aynı_Worker_Key>
MEDIA_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=<Bucket_Endpoint_URL>
S3_BUCKET=<Bucket_Name>
S3_ACCESS_KEY_ID=<Bucket_Access_Key>
S3_SECRET_ACCESS_KEY=<Bucket_Secret_Key>
S3_REGION=us-east-1
```

---

### ADIM 17: Yerel Worker Testi
1. Yerel bağlantı kontrolünü çalıştırın:
   ```cmd
   LOCAL_WORKER_PREFLIGHT.bat
   ```
2. Yerel worker döngüsünü test edin:
   ```cmd
   REELS_AI_LOCAL_WORKER.bat
   ```
