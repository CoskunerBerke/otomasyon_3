# Devam — Reels AI Factory (4 Eylül 2026, sabah)

Repo: `C:\Users\berke\OneDrive\Masaüstü\Projeler\Otomasyon_3`
Branch: **`stale-artifact-guard`** — `main`'e **HENÜZ MERGE EDİLMEDİ**.
Son commit `73b06f2`. PR: https://github.com/CoskunerBerke/otomasyon_3/pull/new/stale-artifact-guard

⚠️ **İlk iş bu PR'ı merge et.** İçinde gece boyunca canlı üretimde bulunan gerçek hataların
düzeltmesi var; merge edilmezse bir sonraki çalıştırma aynı hatalara düşer. Bu repoda
düzeltmelerin dalda mahsur kalması daha önce yaşandı.
düzeltmesi var; merge edilmezse bir sonraki çalıştırma aynı hatalara düşer. Bu repoda
düzeltmelerin dalda mahsur kalması daha önce yaşandı.

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

Gece 3→4 Eylül'de iki hafta da sıfırdan üretilip yayına planlandı. **Açık iş yok.**

| Hafta | Slotlar | Üretim | YouTube | TikTok | Instagram |
|---|---|---|---|---|---|
| `2026-W37` (BuildVerse) | 7–13 Eyl | 14/14 | 14/14 | 14/14 | 14/14 |
| `CBM-2026-W36` (craftsbyman) | 4–10 Eyl | 14/14 | 14/14 | 14/14 | kapalı |

28 video üretildi, 56 yayın planlandı. Bir sonraki hafta için sadece `.bat`:
BuildVerse 14 Eylül'den, craftsbyman 11 Eylül'den başlar (kod son planlı slotun ertesini bulur).

Önceki haftalar (BuildVerse W34–W36, CBM-W34) tamam. **`CBM-2026-W35` bilerek terk edildi**
(operatör kararı, 4 Eyl 00:30): yarım kalmıştı, tamamlamak yerine yeni haftaya geçildi.
14 üretilmiş videosu `workspace/segments/CBM-REEL-2026-00{15..28}` altında kullanılmadan
duruyor. YouTube'da 11'i, TikTok'ta 7'si planlı.

---

## ⚠️ YouTube günlük yükleme kotası — gecenin en pahalı dersi

Craftsbyman'ın YouTube'u 12/14'te takıldı ve saatlerce yanlış teşhis edildi. Gerçek sebep
**doğrulanmamış kanalın günlük yükleme sınırı**ydı. Operatör tek seferlik doğrulamayı
yapınca kalan 2 Reel ilk denemede, tek hata satırı olmadan geçti.

Kotanın belirtileri şunlardı — **bir daha görülürse önce kotayı düşün**:

```
YOUTUBE_UPLOAD_COMPLETION_UNCONFIRMED: no enabled Next button after 120s
[REMOTE_ID] Video ID 20s icinde okunamadi
YOUTUBE_DIALOG_SCRIM_STILL_UP
YOUTUBE_TITLE_FILL_FAILED
```

Yanıltıcı olan: bu zincir tam olarak bir UI hatası gibi görünüyor. Video karşıya geçiyor
(başlık kutusunda YouTube'un dosya adından türettiği isim beliriyor), ama işleme
tamamlanmadığı için diyalog yükleme modunda kalıyor, scrim çekilmiyor, başlık yazılamıyor.
Her başarısız deneme kanalda bir taslak bırakıyor.

Kod bu durumu kotadan ayırt edemiyor. **İyileştirme fırsatı:** yükleme tamamlanmıyorsa
sayfadaki "Günlük yükleme sınırına ulaşıldı" uyarısını arayıp `YOUTUBE_DAILY_QUOTA_REACHED`
ile durmak — 14 Reel'i tek tek denemekten ve taslak biriktirmekten iyi.

---

## Gece düzeltilenler (hepsi `stale-artifact-guard` dalında)

1. **FFmpeg PATH'te görünmüyordu.** Kurulu ve kullanıcı PATH'inde kayıtlı; Claude'un
   başlattığı süreç PATH güncellenmeden önce açıldığı için göremiyordu. Operatör kendi
   terminalinden `.bat`'a bassa çıkmayacak bir hata. *Kod değişikliği yok.*
2. **Sessiz mock fallback** (`concatenator.py:98`) — FFmpeg yokken segment byte'larını
   yapıştırıp "30 saniyelik final video oluşturuldu" diyordu; dosya 10 saniyelik bozuk bir
   MP4'tü. QC'nin de çalışmaması yayına gitmesini engelledi. **HÂLÂ AÇIK:** ffprobe kurulu
   olup ffmpeg olmayan bir makinede sessizce geçer. Yapılacak iş.
3. **Bayat artifact indirme** (`page.py`, `54eb61d`) — Flow üretimi başarısız olunca ekranda
   kalan önceki videoyu "yeni" sanıp indiriyordu; `CBM-REEL-2026-0032`'nin 1. ve 2. segmenti
   birebir aynı dosya çıktı. Artık fingerprint baseline'a karşı doğrulanıyor, ayrıca
   indirilen dosya öncekilerle hash karşılaştırılıyor (`SEGMENT_DUPLICATE`).
4. **Segment resume çalışmıyordu** (`generator.py:140`, `54eb61d`) — `seg.status == "READY"`
   şartı bellekte tutulduğu için süreç ölünce sıfırlanıyor, ödenmiş segmentler yeniden
   üretiliyordu. Artık diskteki dosya kanıt (kopya kontrolüyle).
5. **YouTube başlık alanı tıklanamıyordu** (`youtube_studio_ui_observer.py`, `d83bf45`) —
   `<div class="dialog-scrim ytcp-uploads-dialog">` pointer event'leri yutuyordu. Artık
   scrim'in çekilmesi bekleniyor (kaldırılmıyor, zorlanmıyor — Kural 31). BuildVerse'te
   YouTube'u 14/14 yapan düzeltme bu. **Ama craftsbyman'ın 12/14'ünü açıklayan o değildi**
   — orada scrim de kotanın belirtisiydi. Düzeltme gerçek, teşhis kısmen yanlıştı.
6. **`SCHEDULE_RESUME_REQUIRED` kendi kendini kilitliyordu**
   (`youtube_studio_publisher.py:149`) — `has_remote_evidence` durumun kendisini uzak kanıt
   sayıyor, sistem olmayan taslağı arayıp duruyordu. Bu sefer `progress.json`'da elle
   `PENDING`'e çekilerek aşıldı; **kod düzeltmesi yapılmadı**, kalıcı çözüm gerekiyor.

Testler: `tests/test_flow_stale_artifact.py` (4 yeni), `tests/test_youtube_studio.py` (60, 2'si yeni).

---

## Doğrulanmamış kalanlar (operatör bakabilir, acil değil)

- **YouTube / craftsbyman taslakları** — kota dolduğu dönemdeki başarısız denemeler kanalda
  `postbus archive` / `caravan bakery` adlı taslak bırakmış olabilir. İçerik → Yüklemeler'de
  bak, fazlalık varsa elle sil. Planlı olan ikisi doğru: `VcqiX_XD0Wo`, `HqwHg5Ax4_M`.
- **TikTok hesap doğrulaması** — her Reel'de `ACCOUNT_UNVERIFIED` çıkıyor (her iki markada).
  Hesap adı sayfadan okunamıyor, markaya özel Chrome profiline güvenilerek devam ediliyor.
  28 videonun doğru hesaplarda olduğunu gözle doğrulamak iyi olur.
- **REEL-2026-0059** (`ani-story`, BuildVerse/TikTok) — tek kopya mı? İlk denemede Planla'ya
  basıldı ama ağ kesintisi yüzünden onay görünmedi; ikinci deneme başarılı oldu.

---

## Bilinen, düzeltilmemiş gürültü

- **`CRAFTSBYMAN_SADECE_YOUTUBE.bat` yanlış haftaya sabitlenmiş** — içinde
  `--week-id CBM-2026-W34` yazıyor. Kullanılacaksa hafta elle düzeltilmeli.
- **Telegram bildirimleri** — gece DNS çözülemedi (`getaddrinfo failed`); geçici ağ
  kesintisiydi. Bildirim gitmedi, üretim etkilenmedi.
- **YouTube fazı stdout'a yazmıyor** — ilerlemeyi yalnızca `progress.json`'a yazıyor.
  Log sessizliği "takıldı" sanılabilir; izleme kurarken `progress.json`'ın mtime'ına bak.

---

## Bu sistemin kök örüntüsü (yeni oturum bunu bilsin)

Bir haftada **altı** ayrı olay aynı hatadan çıktı: *bir arayüzü erken okuyup "hazır değil"i
"yok" sanmak.* TikTok dosya girişi, TikTok Planla butonu, YouTube dosya girişi, Instagram
İleri butonu, Flow indirme butonu, YouTube görünürlük hücresi.
**Yedincisi 4 Eylül'de geldi** ve biçimi biraz farklıydı: YouTube başlık kutusu gerçekten
hazırdı, önündeki `dialog-scrim` hazır değildi. Yani örüntü artık sadece "elementi erken
okuma" değil, **"sahneyi erken okuma"** — element hazır olabilir, sahne olmayabilir.

Aynı gece örüntünün **tersi** de görüldü: Flow üretimi başarısız olunca ekranda duran eski
video "yeni" sanıldı. "Hazır değil"i "yok" sanmak kadar, **"eski"yi "yeni" sanmak** da aynı
kökten — arayüze tek bakışta güvenmek, elde karşılaştırılacak bir baseline varken.

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
