# Devam — Reels AI Factory (3 Eylül 2026)

Repo: `C:\Users\berke\OneDrive\Masaüstü\Projeler\Otomasyon_3`
Branch: **`main`** — her şey push edildi, son commit `4b9ef19`. Test paketi **706/706 yeşil**.

**Türkçe cevap ver. Detaylı rapor ver. Canlı çalıştırma (Flow/yayın) sadece açık talimatla.**

---

## Sistem

İki kanal, tek pipeline. Klasörde ne nerede: `README.md` bölüm 0.

| Marka | Kanal | Mod | Platform |
|---|---|---|---|
| `buildverse` | @BuiIdVerse · @kitchenverse360 (TT) · IG | 19:30 `narrative_ambient_story` · 22:00 `cutaway_reveal_story` | YT + TT + IG |
| `craftsbyman` | @craftsbyman | `hidden_build_story` (tek format, hep aynı usta) | YT + TT (IG **kapalı**) |

Her markanın kendi `.bat`'ları var, adları `brand_id`'den türetiliyor:
`BUILDVERSE_GIRIS.bat` · `BUILDVERSE_HAFTALIK_14_REEL.bat` · `BUILDVERSE_SADECE_{YOUTUBE,TIKTOK,INSTAGRAM}.bat`
ve `CRAFTSBYMAN_*` karşılıkları. Ortak: `FLOW_LOGIN.bat`, `INSTALL_FIRST_TIME.bat`.

⚠️ İki haftalık `.bat`'ı **aynı anda çalıştırma** — ikisi de Flow'u port 9222'den kullanıyor.

---

## Nerede kalındı

| Hafta | Slotlar | Üretim | YouTube | TikTok | Instagram |
|---|---|---|---|---|---|
| `2026-W34` buildverse | 17–23 Ağu | 14/14 | 14/14 | 14/14 | 14/14 |
| `2026-W35` buildverse | 24–30 Ağu | 14/14 | 14/14 | 14/14 | 14/14 |
| `2026-W36` buildverse | 31 Ağu–6 Eyl | 14/14 | 14/14 | 14/14 | 14/14 |
| `CBM-2026-W34` | 22–28 Ağu | 14/14 | 14/14 | 14/14 | kapalı |
| **`CBM-2026-W35`** | **29 Ağu–4 Eyl** | 14/14 | **11/14** | **7/14** | kapalı |

### Açık iş: CBM-2026-W35'i tamamlamak

`CRAFTSBYMAN_HAFTALIK_14_REEL.bat` → kaldığı yerden devam eder, planlanmışlara dokunmaz.

Eksikler:

| Reel | Slot | YouTube | TikTok |
|---|---|---|---|
| 0022 | 1 Eyl 22:00 | ✓ | `UPLOAD_ATTEMPTED` |
| 0023–0025 | 2–3 Eyl | ✓ | `PENDING` |
| 0026 | 3 Eyl 22:00 | `FAILED_FATAL` | `PENDING` |
| 0027–0028 | 4 Eyl | `SCHEDULE_RESUME_REQUIRED` | `PENDING` |

Slotların çoğu **geçmişte kaldı** (bugün 3 Eylül). Geçmiş bir slota planlama yapılamaz —
bu Reel'leri kurtarmak yerine haftayı kapatıp yeni haftaya geçmek daha mantıklı olabilir.
Operatöre sor.

`0026` özel: remote_id'si geçen haftanın videosuna (`ry65v75_Hns` = W34/0013) işaret
ediyordu, temizlendi (`workspace/_backups/cross-week-id-*`). `FAILED_FATAL` durumu
haftalar-arası korumanın onu bilinçli olarak durdurduğunu gösteriyor.

---

## 🔴 Operatörün karar vermesi gereken: tekrar eden hafta

**`CBM-2026-W35`'in 14 konseptinin 14'ü de `CBM-2026-W34` ile aynı** — aynı başlıklar,
aynı videolar. Havuzda tam 14 konsept vardı, haftalık ihtiyaç da 14; ikinci hafta
matematiksel olarak birincinin kopyası olmak zorundaydı.

Bu hafta **düzeltmeden önce** planlandı ve 11'i YouTube'da, 7'si TikTok'ta zaten yayında
ya da planlı. Sistem uzak içerik silemez → `MANUAL_REMOTE_CLEANUP_RECOMMENDED`.
Silmek/bırakmak operatörün kararı.

**Bir daha olmaz.** Üç katmanlı düzeltme (`4b9ef19`):
1. Havuzlar büyüdü: `hidden_build` 14→**28**, `cutaway` 12→**16**, `story` 27.
2. Geçen haftanın konseptleri aday havuzundan **çıkarılıyor** (puanlamaya güvenilmiyor —
   çeşitlilik cezası kategori grubuna bakıyor, craftsbyman'de 3 grup var, o yüzden 28
   konsept bile aynı sıralamayı veriyordu).
3. `CONCEPT_POOL_EXHAUSTED` — bir hafta yine de öncekini tekrarlarsa **planlama anında**
   durur, 14 Flow üretimi harcanmadan.

Doğrulandı: iki markada da iki ardışık hafta **sıfır ortak konsept**.

---

## Bu sistemin kök örüntüsü (yeni oturum bunu bilsin)

Bir haftada **altı** ayrı olay aynı hatadan çıktı: *bir arayüzü erken okuyup "hazır değil"i
"yok" sanmak.* TikTok dosya girişi, TikTok Planla butonu, YouTube dosya girişi, Instagram
İleri butonu, Flow indirme butonu, YouTube görünürlük hücresi.

Mekanik kökü: **Playwright'ın `Locator.is_visible(timeout=N)` timeout'unu yok sayar** —
anlık kontroldür, bekleme değil. 17 Ağustos'ta bulunup düzeltilmiş (104 çağrı) ama commit
merge edilmemiş, beş gün boyunca aynı hatalar yaşanmış. Artık main'de; kod tabanında
`is_visible`'a timeout geçen tek çağrı yok.

Bütün bekleme süreleri `tests/test_click_patience.py` ile sabit — hem alt sınır (kimse
kısaltamaz) hem üst sınır (sabır donmaya dönüşemez). **Yedinci bir örnek çıkarsa önce
oraya bak.**

---

## Dallar

`git branch -r --no-merged origin/main` çıktısında görünen ama **içerikleri main'de**
olanlar (cherry-pick edildi, SHA farklı) — tekrar uygulama:
`claude/xenodochial-wu-c9980a`, `claude/infallible-carson-37802d`,
`claude/compassionate-almeida-c9ab2b`, `fix/instagram-worker-timezone`.

Gerçekten merge edilmemiş **özellik** dalları, operatörün kararı:
- `feature/cross-platform-promo` — her platformun açıklamasına diğer iki kanalın linki.
  **Operatör bunu istedi.** Marka sistemi gelmeden yazıldığı için uyarlanması gerek:
  linkler markanın kendi hesaplarından türemeli, kapalı platform tanıtılmamalı.
- `feature/enable-audio-generation` — Flow→QC→yayın hattında ses üretimi.
- `feature/nova-fox-series` — Nova the fox, sezon başına 20 bölüm.

---

## Ürünleştirme yol haritası

Kural: **her adım mevcut iki kanalı bozmadan.** Varsayılanlar bugünkü değerlerde kalır,
her adımdan sonra tam paket yeşil olmalı.

1. ~~Dil~~ **BİTTİ** (`dc936fa`). Tek dilli UI aksiyonu kalmadı;
   `tests/test_selector_language_coverage.py` kuralı sabitliyor.
2. **Sabit değerler — SIRADA.** `Europe/Istanbul`, 19:30/22:00, dosya yolları ayara
   taşınacak; varsayılanlar bugünkü değerler → iki kanal etkilenmez. Düşük risk.
3. **Obsidian'ı opsiyonel yapmak.** Kasa varsa aynen çalışır, yoksa atlanır. Orta risk.
4. **İki state deposu — EN RİSKLİ, EN SONA.** `progress.json` ve `13_PUBLISHING/PUB-*.md`.
   İkincisi "mevcut kanıt her zaman kazanır" dediği için birincisinin temizliği tutmuyor.
   Çelişki raporlanıyor (`STATE_DIVERGENCE`) ama tek kaynağa indirilmedi. Tek seferde
   yapma: önce okuma tarafı, iki tur doğrulama, sonra yazma. Operatöre ayrıca sor.

Koddan bağımsız gerekenler: tek tıklık kurulum (şu an Python + ffmpeg + Chrome + venv),
müşterinin kendi Google Flow erişimi ve kredisi, ve **ToS riski** — üç platformun web
arayüzünü otomatikleştirmek şartlarına aykırı yorumlanabilir; müşterinin kanalı kapanırsa
sorumluluk satıcıya döner.

---

## Kurallar (CLAUDE.md)

- Uzak içerik **asla** otomatik silinmez/değiştirilmez → `MANUAL_REMOTE_CLEANUP_RECOMMENDED`.
- **Kural 31:** UI aksiyonu başına en fazla 2 semantik selector; `force`/JS click/hash
  class yok. DOM gerekiyorsa ve kanıttan çıkarılamıyorsa `NEEDS_USER_HTML` — tahmin etme.
- Aynı anda tek pytest; onarım başına en fazla 2 çalıştırma.
- Reel ID değişmezliği: slot = state = kayıt = dosya adı. Uyuşmazsa `REEL_ID_MEDIA_MISMATCH`.
- `--dry-run` gerçek yayın kaydı taşıyan haftada reddedilir; prova kayıtları damgalanır.
- `.env`, `secrets/`, token'lar asla yazdırılmaz.
