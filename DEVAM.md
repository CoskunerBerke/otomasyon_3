# Devam — Reels AI Factory (21 Ağustos 2026 akşamı)

Bu dosyayı yeni sohbete yapıştır. Repo: `C:\Users\berke\OneDrive\Masaüstü\Projeler\Otomasyon_3`
Branch: `hidden-build-second-channel` (PR yok). Türkçe cevap ver, detaylı rapor ver.

## Sistem

İki kanal, aynı pipeline. Tek komut: ilgili `.bat`.

| Marka | Kanal | Mod | Platform | Durum |
|---|---|---|---|---|
| `buildverse` | @BuiIdVerse | `narrative_ambient_story` | YT+TT+IG | Çalışıyor, W35 (24–30 Ağu) 14/14 tamam |
| `craftsbyman` | @craftsbyman | `hidden_build_story` | YT+TT (IG kapalı) | **Sorunlu, aşağıya bak** |

Marka ayrımı `automation/brands.py`: önek (`CBM-`), ayrı Chrome portları (YT 9234/TT 9233),
ayrı hesap kimliği. Varsayılan marka eski davranışın birebir aynısı.

`.bat` dosyaları: `HAFTALIK_14_REEL_URET_VE_PLANLA.bat` (1. kanal),
`HAFTALIK_14_REEL_CRAFTSBYMAN.bat` (2. kanal), `CRAFTSBYMAN_KANAL_GIRISI.bat` (giriş).

## Acil durum: craftsbyman

Batch `workspace/batches/CBM-2026-W34`, slotlar 22–28 Ağu 19:30 & 22:00.
**14 videonun hepsi diskte** (`workspace/downloads/clean_clean_CBM-REEL-*.mp4`) — üretim gerekmez.

- **CBM-REEL-0001…0007** → `PENDING`. Kanaldan silindiler, 22–25 Ağu slotlarına yüklenmeleri lazım.
- **CBM-REEL-0008…0014** → `SCHEDULED`, kanalda duruyorlar. 0009–0014 tarihleri doğru (26/27/28 Ağu).
- **CBM-REEL-0008** (container→sinema) kanalda **21 Ağu**'da, slotu 25 Ağu 22:00'ydi. Operatörün kararı.

İlk iş: `.bat` ile eksik 7'yi yükle. Kanaldaki 7'ye dokunmaz (SCHEDULED = atlanır).
**İlk 2–3 Reel'i canlıda gözle izle.**

## Bugün ne patladı (tekrarlamasın)

14 planlanan Reel kanalda **28 videoya** dönüştü. İki kusur:

1. `_build_publish_record` kaydı hep `PENDING` kuruyor, `upload_started`ı sadece `remote_id`den
   türetiyordu → ID'si okunamayan 7 Reel "hiç yüklenmemiş" görünüp 30 dk'lık hold'un iki turunda
   baştan yüklendi (14+7+7=28).
2. 0001–0007 aynı `VTMhhYTl9Co` ID'sini paylaşıyordu; ID yakalama bayat tarayıcı URL'ine düşüyor.

İkisi de düzeltildi (commit `9708be0`, `tests/test_no_duplicate_uploads.py`). Operatör 14 kopyayı
elle sildi — bu sistem uzak içerik silemez.

## Asıl iş: kök neden

Operatörün şikayeti: **"her .bat'a basınca hata."** Üç günde aynı kök neden dört kez çıktı —
Flow'un yüklenmemiş sayfası, YouTube'un içerik kontrolü, TikTok'un tarih alanı, YouTube'un video
ID'si. Hepsi aynı: **bir arayüzü bir kez, hemen okuyup "henüz hazır değil"i "yok" sanmak.**
Beklemeler `tests/test_platform_patience.py` içinde sabitli.

Tek tek yama yerine sistematik bakılacak:

1. Eksik 7 Reel'i yükle (üretim yok).
2. **TikTok'ta da kopya var mı kontrol et** — aynı retry mantığı orada da çalışıyor, hiç bakılmadı.
3. Haftanın herhangi bir 7 günlük pencerede sağlam çalışması: yeni marka için başlangıç tarihi
   ("yarın" yerine "üretim bitince en yakın slot") ve slot/atlama mantığı.
4. `--phase youtube` gibi tek faz çalıştırmanın kopya üretmediğini doğrula.
5. Instagram craftsbyman için kapalı (planlama tarafı çalışmıyor, hesap profesyonel olmayabilir).
   Açmak: `brands.py` içinde `platforms` tuple'ına `"instagram"` ekle — geçmiş haftalar otomatik
   "eksik" okunur ve sadece IG'de tamamlanır.

## Kurallar (CLAUDE.md)

- Uzak içerik **asla** otomatik silinmez/değiştirilmez.
- Kural 31: UI aksiyonu başına en fazla 2 semantik selector; `force`/JS click/hash class yok.
  DOM gerekiyorsa ve kanıttan çıkarılamıyorsa `NEEDS_USER_HTML`.
- Aynı anda tek pytest, onarım başına en fazla 2 çalıştırma.
- Canlı çalıştırma (Flow/yayın) sadece açık talimatla.
- Reel ID değişmezliği: slot = state = kayıt = dosya adı. Uyuşmazsa `REEL_ID_MEDIA_MISMATCH`.

## İlk hamle

`workspace/batches/CBM-2026-W34/progress.json` ve manifest'i oku, kanalın gerçek haliyle
karşılaştır, sonra plan sun. Hiçbir şey çalıştırmadan önce durumu doğrula.
