# REELS AI FACTORY — OBSIDIAN + GOOGLE FLOW FULL AUTOMATION

Windows üzerinde çalışan, harici ücretli LLM API (OpenAI, Claude) veya CapCut gerektirmeyen, **Google Flow** web arayüzünü Playwright ile kullanarak tamamen otomatik **sessiz / global satisfying Reels videoları** üreten, teknik kalite kontrolünden geçiren ve Obsidian kasanızla (`Reels_AI_Studio`) senkronize çalışan üretim sistemi.

---

## 1. Sistem Ne Yapıyor?

Masaüstündeki `.bat` dosyasına tıkladığınızda sistem otomatik olarak:

1. **Obsidian Kasasını Okur:** `03_SCRIPTS`, `04_PRODUCTION`, `05_READY`, `06_PUBLISHED`, `07_REJECTED` klasörlerini tarar.
2. **Geçmişi Analiz Eder & Tekrarı Engeller:** Daha önce üretilmiş `topic_key` ve kategorileri çıkarır, yakın semantik benzerlikleri ve son kullanılan kategorileri tespit eder.
3. **Yeni Fikir & İngilizce Prompt Üretir:** 40+ kategoriden (fütüristik şehir, ada tesisi, çöl megakenti, solarpunk, uzay üssü vb.) en yüksek çeşitlilik (diversity) puanına sahip konseptleri seçer ve dikey 9:16 formatında kaliteli İngilizce master prompt hazırlar.
4. **Obsidian Kaydı Açar:** `03_SCRIPTS/REEL-YYYY-NNNN.md` dosyasını otomatik oluşturur.
5. **Google Flow Otomasyonunu Çalıştırır:** Kalıcı tarayıcı profili ile Google Flow'u açar, 9:16 formatını seçer, promptu girer ve üretimi başlatır.
6. **İndirme & Güvenlik Kontrolü:** Üretilen videoyu `workspace/downloads/` altına indirir.
7. **FFmpeg & Görsel Kalite Kontrolü (QC):** 
   - 9:16 en-boy oranını doğrular.
   - Tüm ses kanallarını FFmpeg ile sıfırlar (tamamen sessiz ve temiz video).
   - Faststart bayrağı ekler (sosyal medya optimizasyonu).
   - 5 farklı kareden (0%, 25%, 50%, 75%, 100%) siyah ekran, donma veya bozukluk analizi yapar.
8. **Masaüstüne Kaydeder:** Final MP4 ve eşlik eden detaylı metadata JSON dosyasını `C:\Users\<Kullanıcı>\Desktop\AI_Reels\YYYY-MM-DD\` altına kaydeder.
9. **Obsidian'ı Günceller:** Notu `status: READY` yaparak `05_READY` klasörüne taşır.
10. **Windows Bildirimi Gönderir:** İşlem tamamlandığında sağ altta bildirim gösterir.

---

## 2. Sistem Gereksinimleri

- **İşletim Sistemi:** Windows 10 / 11 (64-bit)
- **Python:** Python 3.10 veya daha yenisi (PATH'e ekli olmalı)
- **FFmpeg & FFprobe:** Sistem PATH'inde kurulu olmalı (`ffmpeg -version` çalışmalı)
- **Google Hesabı:** Google Flow erişimi olan bir Google hesabı
- **Obsidian:** `Reels_AI_Studio` kasası

---

## 3. İlk Kurulum (30 Saniye)

Klasör içindeki:

👉 **`INSTALL_FIRST_TIME.bat`**

dosyasına çift tıklayın.

Bu işlem:
- Python ve FFmpeg kontrollerini yapar.
- `.venv` sanal ortamını oluşturur.
- Gerekli tüm Python kütüphanelerini (`requirements.txt`) kurar.
- Playwright Chromium tarayıcısını indirir.
- `config.local.json` dosyasını hazırlar.

---

## 4. Google Flow'a İlk Giriş (Google Chrome ile Manuel Giriş)

Google'ın otomasyon algılama engeline takılmamak için giriş işlemi doğrudan gerçek Google Chrome üzerinden yapılır:

👉 **`FLOW_LOGIN.bat`**

dosyasına çift tıklayın.
1. Gerçek Google Chrome penceresi dedicated profili ile (`%LOCALAPPDATA%\ReelsAIFactory\chrome-profile`) açılır.
2. Açılan Chrome penceresinde Google hesabınızla tamamen **manuel** olarak oturum açın.
3. Google Flow ana ekranına ulaştığınızdan emin olun.
4. **Google Chrome penceresini AÇIK BIRAKIN.**  
   *(Otomasyon, Playwright `connect_over_cdp` ile bu açık Chrome oturumuna bağlanarak videoları üretecektir.)*

Oturumunuz kalıcı olarak `%LOCALAPPDATA%\ReelsAIFactory\chrome-profile` klasörüne (OneDrive dışında) kaydedilir. Artık sonraki üretimlerde sizden tekrar şifre istenmez.

---

## 5. Kredi Harcamadan Test (Dry Run)

Sistem mantığını, Obsidian okumasını ve prompt üretimini sıfır kredi harcayarak test etmek için:

```powershell
python automation\run.py --count 1 --dry-run
```

veya sanal ortamda:

```powershell
.venv\Scripts\python automation\run.py --count 1 --dry-run
```

Bu modda Obsidian kasası taranır, sıradaki Reel ID'si belirlenir, yeni bir konsept seçilip `03_SCRIPTS/` altına not yazılır; fakat **tarayıcı açılmaz ve video üretilmez.**

---

## 6. Günlük Kullanım (1-Click Desktop Automation)

Masaüstünde tek tıkla video üretmek için iki hazır batch dosyası mevcuttur:

### 1 Video Üretmek İçin (Test & Güvenli Üretim):
👉 **`1_YENI_REEL_URET.bat`**

### 3 Video Üretmek İçin (Günlük Toplu Üretim):
👉 **`3_YENI_REEL_URET.bat`**

---

## 7. Çıktılar Nerede Saklanır?

Başarılı videolar otomatik olarak Windows'un gerçek Masaüstü (OneDrive yönlendirmesi dahil) klasörüne tarih bazlı kaydedilir:

`<GERÇEK_WINDOWS_MASAÜSTÜ>\AI_Reels\YYYY-MM-DD\`  
*(Örn: `C:\Users\berke\OneDrive\Masaüstü\AI_Reels\2026-08-15\`)*

Örnek çıktı:
- `REEL-2026-0003_Luxury_Island_Resort.mp4` *(Sessiz, 9:16, Faststart optimize MP4)*
- `REEL-2026-0003_Luxury_Island_Resort.json` *(Tüm prompt, çözünürlük, süre, QC ve üretim zamanı metadata kaydı)*

---

## 8. Obsidian Kasası Entegrasyonu

Otomasyon `Reels_AI_Studio` kasasını şu yaşam döngüsüyle yönetir:

1. **`03_SCRIPTS/REEL-YYYY-NNNN.md`**: Yeni fikir ve prompt oluşturulduğunda (`status: PROMPT_READY`).
2. **`04_PRODUCTION/REEL-YYYY-NNNN.md`**: Google Flow'a gönderildiğinde (`status: GENERATING`).
3. **`05_READY/REEL-YYYY-NNNN.md`**: Video üretilip QC'den geçtiğinde dosya yolu ve metadata eklenerek taşınır (`status: READY`).
4. **`07_REJECTED/REEL-YYYY-NNNN.md`**: Herhangi bir teknik hata veya QC reddinde hata sebebiyle buraya taşınır (`status: REJECTED`).

Ayrıca kasaya iki standart kılavuz dosyası yerleştirilmiştir:
- `00_SYSTEM/SILENT_VISUAL_RULES.md`
- `09_TEMPLATES/SILENT_REEL_TEMPLATE.md`

---

## 9. Flow UI Değişirse Ne Yapılır?

Google Flow web arayüzünde butonların yerleri veya isimleri değişirse:

1. **Hata Ekran Görüntüsünü İnceleyin:**
   Playwright bir öğeyi bulamadığında otomatik olarak `screenshots/errors/` klasörüne tam ekran görüntüsü ve sayfa HTML'ini kaydeder.
2. **Merkezi Seçicileri Güncelleyin:**
   `automation/flow/selectors.py` dosyasını açarak ilgili buton veya metin seçicisini ekleyin.
   Örnek:
   ```python
   GENERATE_BUTTON_SELECTORS = [
       "button:has-text('Generate')",
       "button:has-text('Create Video')",  # Yeni eklenen alternatif
   ]
   ```

---

## 10. CAPTCHA / Yeniden Giriş Durumu (`USER_ACTION_REQUIRED`)

Sistem bot korumalarını bypass etmeye çalışmaz. Eğer:
- Google oturumu zaman aşımına uğrarsa,
- Güvenlik doğrulaması veya CAPTCHA çıkarsa,

Otomasyon güvenli bir şekilde durur, konsolda `[USER_ACTION_REQUIRED]` uyarısı verir ve Windows bildirimi gönderir:
> *"Google Flow kullanıcı müdahalesi bekliyor."*

Bu durumda:
1. `FLOW_LOGIN.bat` dosyasını çalıştırın.
2. Açılan pencerede doğrulamayı tamamlayıp tarayıcıyı kapatın.
3. Otomasyonu tekrar başlatın.

---

## 11. Güvenlik ve Kredi Limitleri

- **Hard Safety Cap:** `--count` parametresine 100 bile verilse sistem maksimum 5 video üretir (`MAX_VIDEOS_PER_RUN = 5`).
- **Tekil Çalışma Kilidi:** `automation.lock` dosyası sayesinde aynı anda iki batch dosyasının çalışıp kredileri çift tüketmesi engellenir.
- **Sıralı Üretim:** Videolar paralel değil, sırayla (Video 1 -> Tamamla -> QC -> Video 2) üretilir.
- **Retry Limiti:** Teknik aksaklıklarda maksimum 1 defa tekrar denenir (`MAX_RETRIES_PER_VIDEO = 1`), sonsuz döngüye girilmez.

---

## 12. Yapılandırma (`config.local.json`)

```json
{
  "vault_path": "C:\\Users\\berke\\obsidian\\Reels_AI_Studio",
  "output_path": "%USERPROFILE%\\Desktop\\AI_Reels",
  "videos_per_run": 1,
  "video_duration": 5,
  "video_ratio": "9:16",
  "audio_enabled": false,
  "generation_timeout_minutes": 20,
  "max_retries_per_video": 1,
  "browser_headless": false,
  "reject_wrong_ratio": true,
  "flow_url": "https://labs.google/fx/tools/flow"
}
```

---

## 13. Testlerin Çalıştırılması

Tüm birim testleri (ID üretimi, çeşitlilik puanlaması, prompt motoru, Obsidian okuma/yazma, FFprobe QC, 3x10s V3 mimarisi, Multi-Agent MessageBus ve Graph Node testleri) çalıştırmak için:

```powershell
pytest -v tests/
```

---

## 14. AGENT CONTROL CENTER VE GRAPH VIEW NASIL KULLANILIR?

Reels AI Factory, arka planda çalışan deterministik Agent'ların durumlarını, aralarındaki gerçek mesajları ve üretim akışını Obsidian içinde **canlı bir dashboard** ve **interaktif bir Knowledge Graph** olarak görselleştirir.

### 🚀 Kullanım Adımları:

1. **Obsidian'ı Açın:** `Reels_AI_Studio` kasanızı açın.
2. **Control Center'ı Açın:** Kasa kök dizinindeki `AGENT_CONTROL_CENTER.md` dosyasını açın (veya sağ panele sabitleyin).
3. **Üretimi Başlatın:** Masaüstünden `1_YENI_REEL_URET.bat` veya `3_YENI_REEL_URET.bat` dosyasına tıklayın.
4. **Canlı Durumu İzleyin:**
   - `CONTENT_DIRECTOR`: Üretim planını ve batch koordinasyonunu yürütür.
   - `HISTORY_AGENT`: Geçmiş videoları analiz edip çeşitlilik kriterlerini belirler.
   - `IDEA_AGENT`: Özgün konsepti seçer.
   - `SEGMENT_PLANNER_AGENT`: 3 aşamalı (10s x 3) inşa planını hazırlar.
   - `FLOW_AGENT`: Google Flow üzerinde segmentleri sırayla üretip indirir.
   - `QUALITY_AGENT`: Kalite kontrol, ses temizleme ve 30s final FFmpeg birleştirmesini yapar.
   - `LAST AGENT MESSAGE`: En son gerçekleşen Agent mesajını gösterir.

### 🌐 Obsidian Graph View Kullanımı:

1. **Graph View'u Açın:** Sol menüden **Open graph view** butonuna tıklayın veya `Ctrl + G` kısayolunu kullanın.
2. **Global Graph vs. Local Graph:**
   - **Global Graph:** Tüm kasanın genel bağlantı ağını gösterir. Zamanla üretilen yüzlerce Reel, Segment ve Run burada devasa bir bilgi kümesi oluşturur.
   - **Local Graph:** Herhangi bir Agent veya Reel notu açıkken sağ menüden **Open local graph** seçeneğini açın.
     - `FLOW_AGENT` Local Graph'ı: Flow'un ürettiği tüm segmentleri, ilgili Reel'leri ve QC mesajlarını gösterir.
     - `IDEA_AGENT` Local Graph'ı: Seçilen konseptleri, History Agent ve Segment Planner ile bağlantılarını gösterir.
3. **Graph Filtreleri & Grupları (Graph Settings):**
   - **Path Filtreleri:**
     - Sadece Agentlar için: `path:"00_AGENTS"`
     - Sadece Run'lar için: `path:"10_AGENT_RUNS"`
     - Sadece Mesajlar için: `path:"11_AGENT_MESSAGES"`
     - Sadece Segmentler için: `path:"12_SEGMENTS"`
   - **Color Groups (Renk Gruplama):**
     - `tag:#agent` -> Mavi (8 Temel Agent)
     - `tag:#reel` -> Yeşil (Reel Ana Notları)
     - `tag:#segment` -> Sarı (10s İnşa Segmentleri)
     - `tag:#run` -> Mor (Batch Çalıştırmaları)
     - `tag:#agent-message` -> Turuncu (Önemli Mesaj Düğümleri)
4. **Klasör Yapısı:**
    - `00_AGENTS/`: 8 Agent tanımı ve `AGENT_ARCHITECTURE.md` mimari diyagramı.
    - `10_AGENT_RUNS/`: Her batch çalıştırmasının zaman çizelgesi ve bağlı Reel'ler.
    - `11_AGENT_MESSAGES/`: Kronolojik mesaj kütükleri ve önemli dönüm noktası mesaj düğümleri.
    - `12_SEGMENTS/`: Her 30s Reel'in 3 parçalık inşa aşama düğümleri (`REEL-XXXX_SEGMENT-01`, `02`, `03`).
5. **Graph Neden Zamanla Büyüyecek?:**
   - Her üretilen yeni Reel; 1 Run bağlantısı, 3 Segment düğümü (birbirine zincirli), sorumlu Agent bağlantıları ve milestone mesajları ile Graph'a organik olarak eklenir. Hiçbir manuel bağlantı kurmanıza gerek kalmadan sistem kendini yaşayan bir yapay zeka fabrikası ağına dönüştürür.

---

## 15. YOUTUBE + TIKTOK YAYINLAMA SİSTEMİ (PUBLISHING AGENT V1)

Reels AI Factory V1 Publishing Layer, `05_READY` klasöründe hazır bulunan 30 saniyelik 9:16 final videoları **YouTube Shorts** ve **TikTok Studio** platformlarına otomatik metadata ile yükler ve platformların kendi yerel zamanlayıcılarına (**Native Scheduling**) kaydeder.

Schedule işlemi bir kez başarıyla tamamlandıktan sonra, **yayın saatinde bilgisayarınızın açık olması gerekmez.**

---

### 🔑 1. Kurulum ve İlk Girişler

#### A. YouTube Shorts Kurulumu (Resmi YouTube Data API v3):
1. **Google Cloud Console** üzerinde bir proje oluşturun ve **YouTube Data API v3** servisini aktif edin.
2. **OAuth 2.0 İstemci Kimliği** (Masaüstü Uygulaması) oluşturup JSON dosyasını indirin.
3. İndirdiğiniz dosyayı projenin içine şu adla kopyalayın:
   👉 `secrets/youtube/client_secret.json`
4. İlk yetkilendirme için:
   👉 **`YOUTUBE_LOGIN.bat`** dosyasını çalıştırın.
5. Açılan tarayıcıda YouTube kanalınızın bağlı olduğu Google hesabıyla giriş yapıp yetki verin. Token güvenli bir şekilde `secrets/youtube/token.json` dosyasına kaydedilir (`.gitignore` korumalıdır).

#### B. TikTok Studio Kurulumu (İzole Chrome Profili):
- TikTok için Flow profilinden tamamen ayrı, izole bir profil kullanılır (`%LOCALAPPDATA%\ReelsAIFactory\tiktok-profile`) ve **Port 9223** üzerinden çalışır (Flow portu 9222 ile asla karışmaz).
- İlk giriş için:
  👉 **`TIKTOK_LOGIN.bat`** dosyasını çalıştırın.
- Açılan Chrome penceresinde TikTok hesabınıza manuel olarak giriş yapın. Oturum kalıcı olarak profilde saklanır.

---

### ⚙️ 2. Yapılandırma (`publishing.local.json` veya `config.local.json`)

```json
{
  "publishing": {
    "enabled": true,
    "timezone": "Europe/Istanbul",
    "platforms": ["youtube", "tiktok"],
    "daily_slots": ["18:00", "20:00"],
    "schedule_start_date": "2026-08-20",
    "youtube_enabled": true,
    "tiktok_enabled": true,
    "ai_disclosure": true
  }
}
```

* **`timezone`**: Saat dilimi (`Europe/Istanbul`). Tüm UTC/yerel saat dönüşümleri timezone-aware olarak hesaplanır.
* **`daily_slots`**: Günde kaç video yayınlanacağını ve saatlerini belirler (Örn: `["18:00", "20:00"]` -> Günde 2 slot).
* **`schedule_start_date`**: Yayınların başlayacağı ilk gün (`YYYY-MM-DD`). **NULL ise kazara hemen yayınlama yapılmasını engellemek için sistem çalışmayı güvenli şekilde reddeder.**

---

### 🚀 3. Yayınlama Komutları (1-Click Desktop Automation)

* **1 READY Videoyu Planlamak İçin:**
  👉 **`1_READY_VIDEOYU_PLANLA.bat`**
  *(En eski yayınlanmamış 1 READY videoyu seçer, YouTube ve TikTok için sonraki boş slota planlar).*

* **14 Videoyu (Haftalık Seri) Planlamak İçin:**
  👉 **`14_VIDEOYU_PLANLA.bat`**
  *(7 gün × günde 2 slot = 14 videoluk yayın takvimini sırayla oluşturur).*

* **Kredi/Upload Harcamadan Test Etmek İçin (Dry-Run):**
  ```powershell
  python automation/publish.py --count 1 --dry-run
  python automation/publish.py --count 14 --dry-run
  ```

---

### 🛡️ 4. Güvenlik, İdempotency ve Retry Mimarisi

1. **İdempotency (Çift Yükleme Koruması):**
   - Her Reel için `reel_id + platform` anahtarı ve video `SHA256` parmak izi takip edilir.
   - Durumu `SCHEDULED` veya `PUBLISHED` olan bir platform kaydı asla yeniden yüklenmez.
2. **Hata İzolasyonu (Failure Isolation):**
   - Örneğin YouTube başarılı (`SCHEDULED`) ama TikTok başarısız (`FAILED`) olduysa; yeniden çalıştırmada YouTube **atlanır (SKIP)**, sadece TikTok **tekrar denenir (RETRY)**.
3. **Fail-Safe Scheduling:**
   - TikTok arayüzünde Schedule/Planla seçeneği bulunamazsa veya oturum düşmüşse video **asla hemen yayınlanmaz (Post butonuna basılmaz)**; durum `SCHEDULING_UNAVAILABLE` veya `AUTH_REQUIRED` olarak işaretlenir.
4. **AI İçerik Bildirimi (Synthetic Media Disclosure):**
   - YouTube Data API v3 üzerinde `containsSyntheticMedia: true` bayrağı iletilir.
   - TikTok Studio üzerinde yapay zekâ içerik etiketi otomatik açılır.

---

### 📊 5. Obsidian Publishing Queue & Knowledge Graph

- **`13_PUBLISHING/PUBLISHING_QUEUE.md`**: Tüm videoların YouTube ve TikTok planlama durumlarını canlı bir tablo halinde gösterir.
- **`13_PUBLISHING/PUB-REEL-XXXX-PLATFORM.md`**: Her platform yüklemesi için remote video ID, link, SHA256 ve zaman bilgisini saklar.
- **`AGENT_CONTROL_CENTER.md`**: Yayınlama başladığında `PUBLISH_AGENT`'ı `RUNNING` durumunda ve aktif platform işlemiyle birlikte gösterir.
- **Graph View Bağlantıları:**
  `[[PUBLISH_AGENT]]` → `[[PUB-REEL-2026-0012-YOUTUBE]]` → `[[REEL-2026-0012]]`
  şeklinde organik bir yayınlama ağı (Publishing Cluster) oluşturur.
