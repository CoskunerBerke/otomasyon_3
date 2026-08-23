# Devam — Reels AI Factory (22 Ağustos 2026)

Bu dosyayı yeni sohbete yapıştır. Repo: `C:\Users\berke\OneDrive\Masaüstü\Projeler\Otomasyon_3`
Branch: **`main`** — 22 Ağustos'ta `hidden-build-second-channel` (23 commit) main'e
fast-forward edildi ve push edildi. Türkçe cevap ver, detaylı rapor ver.

### Dallar

Şu dallar `git branch -r --no-merged origin/main` çıktısında görünür ama **içerikleri
main'de** (commit'leri cherry-pick edildiği için SHA'ları farklı) — tekrar uygulama:
`claude/xenodochial-wu-c9980a`, `claude/infallible-carson-37802d`,
`claude/compassionate-almeida-c9ab2b`, `fix/instagram-worker-timezone`.

Gerçekten merge edilmemiş olanlar **özellik** dalları, operatörün kararı:
`feature/enable-audio-generation` (Flow→QC→yayın ses üretimi),
`feature/cross-platform-promo` (açıklamalarda diğer iki kanalın tanıtımı),
`feature/nova-fox-series` (Nova the fox, sezon başına 20 bölüm).

## Sistem

İki kanal, aynı pipeline. Klasörde ne nerede: `README.md` bölüm 0.

| Marka | Kanal | Mod | Platform | Durum |
|---|---|---|---|---|
| `buildverse` | @BuiIdVerse | `narrative_ambient_story` | YT+TT+IG | W35 (24–30 Ağu) 14/14 tamam |
| `craftsbyman` | @craftsbyman | `hidden_build_story` | YT+TT (IG kapalı) | W34 (22–28 Ağu) 14/14 tamam |

Marka ayrımı `automation/brands.py`: önek (`CBM-`), ayrı Chrome portları (YT 9234/TT 9233),
ayrı hesap kimliği. Varsayılan marka eski davranışın birebir aynısı.

## Nerede kalındı: CBM-2026-W34 (22–28 Ağustos)

14 video da diskte, üretim gerekmiyor. Manifest `LOCKED`.

**Hafta bitti: YouTube 14/14, TikTok 14/14.** 22–28 Ağustos, her gün 19:30 ve 22:00.
Operatör iki kanalda da gözle doğruladı. Açık iş yok.

- YouTube'da 14 benzersiz remote ID, çakışma yok.
- TikTok'u tamamlayan iki düzeltme: `file input not found` (12. Reel) ve Planla
  butonuna kaydırırken 1,5 sn'de pes etme (13. Reel).
- **Instagram** bu marka için kapalı. Açmak: `brands.py` içinde `platforms` tuple'ına
  `"instagram"` ekle — geçmiş haftalar otomatik "eksik" okunur ve sadece IG'de tamamlanır.

### Elle müdahale gereken iki şey (sistem uzak içerik silemez)

1. **Tram videosu YouTube'da iki kez var.** Biri 21 Ağu'da yayınlandı (elle temizlikten
   kurtulmuş bir kopya), aslı 27 Ağu 19:30'da tekrar çıkacak. Karar senin:
   27 Ağu'dakini silersen tekrar olmaz ama o slot boş kalır.
2. **25 Ağu 22:00 YouTube'da boş** — CBM-REEL-0008 oraya gidecekti, 21 Ağu'da çıktı.

## Bu turda düzeltilenler

`f13e149` · `d43fda4` · `b65a214` · `907a539` — hepsi push edildi.

- Silinmiş bir videoya kilitlenen `remote_id` (7 Reel'i dört gün boş bıraktı).
  `open_exact_remote_video` artık hata sayfasını video sanmıyor.
- Çakışma koruması artık her dönen ID'yi kapsıyor; TikTok'un sabit işareti muaf
  (yoksa TikTok her hafta ikinci Reel'de dururdu).
- `upload_file` sayfanın kurulmasını bekliyor (12. Reel'de duran hata).
- TikTok doğrulaması artık caption'a bakıyor, başlığa değil.
- Yeni hafta bugün başlayabiliyor — günün slotları hâlâ önümüzdeyse gün çöpe gitmiyor.
- `--dry-run` gerçek yayın kaydı taşıyan bir haftaya artık **reddediliyor**.
- İki state deposu çeliştiğinde artık çıktıda görünüyor (`STATE_DIVERGENCE`).

## Uçtan uca denetim (22 Ağustos gecesi)

Yayın yolunun tamamı tarandı: kritik yoldaki her fonksiyon "yokluk kararını sabırla mı
veriyor" diye denetlendi. Bulunan 6 kusur düzeltildi (`97abca8`).

**En ağır ikisi yanlış kanala yayın riskiydi.** Her iki hesap koruması da okunamayınca
`"assumed active"` deyip True dönüyordu, ve ikisinde de kanal 1'in adı (`buildverse` /
`kitchenverse`) hangi marka çalışırsa çalışsın kabul ediliyordu. Bu fallback tembellik
değildi: kanal 1'in handle'ı `@BuiIdVerse` — büyük İ ile — görünen adı ise "BuildVerse".
Karakter katlamasıyla çözüldü (ikisi de `bu11dverse`, `craftsbyman` kendine).
YouTube artık okuyamazsa reddediyor; TikTok reddetmiyor (Kural 31: göremediğimiz DOM'u
tahmin etmiyoruz) ama artık "doğrulandı" da demiyor.

Diğer dördü: `upload_file` tek bakışta "yok" diyordu (TikTok'u 12. Reel'de durduran
hatanın aynısı, YouTube'da da vardı); `fill_details` başlık yazılamasa bile True dönüyordu
(Reel dosya adıyla yayınlanırdı); `is_editor_open_for_reel` `"oasis"` kelimesini
eşleştiriyordu (bir Reel'in başlığını başka bir videoya yapıştırabilirdi);
`wait_for_upload_completion` timeout'ta da başarı bildiriyordu.

**Test paketi zaten kırmızıydı** — 7 hata. Hepsi bilinçli değişikliklerden kalmış bayat
iddialar; asıl niyetleri korunarak güncellendi. Biri ise sadece test sırasına bağlıydı:
`CloudConfig` reponun `.env`'ini `os.environ`'a kalıcı yazıyor, dolayısıyla ilk kim
`CloudConfig` kurarsa "güvenli varsayılan"ı o belirliyor. **Paket artık 675/675 yeşil.**

## Kök nedenin kökü (22 Ağustos)

Playwright'ın `Locator.is_visible(timeout=N)` **timeout'unu yok sayar** — anlık kontroldür,
bekleme değil. Yani `is_visible(timeout=2000)` yazan her yer aslında hiç beklemiyordu ve
henüz render olmamış elemanı "yok" sayıyordu. Bir haftalık "bulunamadı" hatalarının
tamamının altındaki mekanik sebep buydu.

**Bu 17 Ağustos'ta zaten bulunmuş ve düzeltilmiş** (`1a1ee1f`, 104 çağrı noktası), ama
o commit hiç merge edilmemiş — `claude/xenodochial-wu-c9980a` dalında duruyordu. Beş
günlük olayların hepsi, push edilmiş bir dalda bekleyen düzeltmenin ardından yaşandı.

Cherry-pick edildi (`bfde795`): 97 çağrı temiz birleşti, 7 çakışma sonradan yazılan
kodda çıktı ve yeni bekleme döngüleri korunarak çözüldü. Kalan 13'ü ortak bir yardımcıdan
(`automation/publishing/ui_wait.py`) geçiyor; bu yardımcı yalnızca `is_visible` uygulayan
test sahtelerinde anlık kontrole düşüyor. **Artık `is_visible`'a timeout geçen tek bir
çağrı kalmadı.** Ayrıca `.bat`'ların hâlâ önerdiği `--dry-run` tuzağı kapatıldı: prova
kayıtları damgalanıyor, canlı çalıştırma onları "yapılmış" saymıyor.

Paket: **683/683 yeşil.**

## Asıl hedef: satılabilir hale getirmek

Operatörün amacı bu otomasyonu hem başkalarına satmak hem kendi yeni kanallarında
farklı senaryolarla çalıştırmak. Flow üretim tarafı sorunsuz; kırılganlık hep
yükleme-planlama tarafında.

**Kök örüntü:** otomasyon olgun bir hesabın arayüzüne göre sertleştirilmiş. Yeni hesap
ilk açılışta tanıtım turu / bilgilendirme kartları gösteriyor, bunlar bir kez çıkıp bir
daha çıkmıyor — ne HTML'i alınabiliyor ne tekrar test edilebiliyor. Çözüm selector
kovalamak değil: `CRAFTSBYMAN_GIRIS.bat` artık yayıncının kullandığı sayfayı
açıyor, insan turu bir kez elle geçiyor, otomasyon olgun bir hesap görüyor.

### Ürünleştirme yol haritası

Kural: **her adım mevcut iki kanalı bozmadan.** Varsayılanlar bugünkü değerlerde kalır,
her adımdan sonra tam paket yeşil olmalı.

1. **Dil — BİTTİ** (`dc936fa`). TikTok içerik-kontrolü modalının iki listesi iki dilli
   yapıldı; başka tek dilli UI aksiyonu kalmadı. Kural artık
   `tests/test_selector_language_coverage.py` ile sabit: bir aksiyon Türkçe metne
   dayanabilir ama tek yolu o olamaz. "Hemen paylaş'a basma" blocklist'leri için ayrı ve
   daha sıkı kural (buton metnine bakıldığı için iki dili de bilmek zorunda).
2. **Sabit değerler — SIRADA.** `Europe/Istanbul`, 19:30/22:00 slotları, dosya yolları.
   Ayara taşınacak, varsayılanlar bugünkü değerler → iki kanal etkilenmez. Düşük risk.
3. **Obsidian'ı opsiyonel yapmak.** Kasa varsa aynen çalışır, yoksa adım atlanır. Orta risk.
4. **İki state deposu — EN RİSKLİ, EN SONA.** `progress.json` ve
   `13_PUBLISHING/PUB-*.md`. İkincisi "mevcut kanıt her zaman kazanır" dediği için
   birincisinin temizliği tutmuyor; çelişki şu an raporlanıyor ama tek kaynağa
   indirilmedi. Yapılırken tek seferde değil: önce yalnızca okuma tarafı, iki tur
   doğrulama, sonra yazma tarafı. Operatöre ayrıca sorulacak.

Satmadan önce koddan bağımsız gerekenler: tek tıklık kurulum (şu an Python + ffmpeg +
Chrome + venv), müşterinin kendi Google Flow erişimi ve kredisi, ve **ToS riski** —
YouTube/TikTok/Instagram web arayüzünü otomatikleştirmek üç platformun da şartlarına
aykırı yorumlanabilir; müşterinin kanalı kapanırsa sorumluluk satıcıya döner.

**Operatör kararı (22 Ağu): 2. adıma geçilmedi, bir sonraki haftalık çalıştırma
beklenecek.** O çalıştırmada ilk 2-3 Reel gözle izlenmeli — bu haftaki bütün
düzeltmelerin gerçek sınavı odur.

## Disk

`workspace/` 1.1 GB (segmentler 641 MB, downloads 385 MB) — CLAUDE.md bunları korumayı
şart koşuyor, **silme**. `screenshots/` 22 Ağustos'ta temizlendi: kapanmış olaylara ait
231 dosya (114 MB) silindi, bugünün 142 dosyası (23 MB) duruyor.

Operatör kararı (22 Ağu): hafta, günün ilk slotu 6+ saat ilerideyse **bugünden**
başlayabilir — `SAME_DAY_START_LEAD_HOURS`.

## Kurallar (CLAUDE.md)

- Uzak içerik **asla** otomatik silinmez/değiştirilmez.
- Kural 31: UI aksiyonu başına en fazla 2 semantik selector; `force`/JS click/hash class yok.
  DOM gerekiyorsa ve kanıttan çıkarılamıyorsa `NEEDS_USER_HTML`.
- Aynı anda tek pytest, onarım başına en fazla 2 çalıştırma.
- Canlı çalıştırma (Flow/yayın) sadece açık talimatla.
- Reel ID değişmezliği: slot = state = kayıt = dosya adı. Uyuşmazsa `REEL_ID_MEDIA_MISMATCH`.
