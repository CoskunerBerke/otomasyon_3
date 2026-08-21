# Devam — Reels AI Factory (22 Ağustos 2026)

Bu dosyayı yeni sohbete yapıştır. Repo: `C:\Users\berke\OneDrive\Masaüstü\Projeler\Otomasyon_3`
Branch: `hidden-build-second-channel` (PR yok). Türkçe cevap ver, detaylı rapor ver.

## Sistem

İki kanal, aynı pipeline. Klasörde ne nerede: `README.md` bölüm 0.

| Marka | Kanal | Mod | Platform | Durum |
|---|---|---|---|---|
| `buildverse` | @BuiIdVerse | `narrative_ambient_story` | YT+TT+IG | W35 (24–30 Ağu) 14/14 tamam |
| `craftsbyman` | @craftsbyman | `hidden_build_story` | YT+TT (IG kapalı) | YT 14/14 · TT 11/14 |

Marka ayrımı `automation/brands.py`: önek (`CBM-`), ayrı Chrome portları (YT 9234/TT 9233),
ayrı hesap kimliği. Varsayılan marka eski davranışın birebir aynısı.

## Nerede kalındı: CBM-2026-W34 (22–28 Ağustos)

14 video da diskte, üretim gerekmiyor. Manifest `LOCKED`.

- **YouTube 14/14 tamam** — 14 benzersiz remote ID, çakışma yok.
- **TikTok 11/14** — 0001–0011 planlandı ve tarihleri doğru. **0012, 0013, 0014 eksik.**
  Kaldığı yerden devam etmek için: `CRAFTSBYMAN_SADECE_TIKTOK.bat`.
  Durduran hata (`file input not found`) düzeltildi; planlı Reel'ler atlanır.
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

## Asıl hedef: satılabilir hale getirmek

Operatörün amacı bu otomasyonu hem başkalarına satmak hem kendi yeni kanallarında
farklı senaryolarla çalıştırmak. Flow üretim tarafı sorunsuz; kırılganlık hep
yükleme-planlama tarafında.

**Kök örüntü:** otomasyon olgun bir hesabın arayüzüne göre sertleştirilmiş. Yeni hesap
ilk açılışta tanıtım turu / bilgilendirme kartları gösteriyor, bunlar bir kez çıkıp bir
daha çıkmıyor — ne HTML'i alınabiliyor ne tekrar test edilebiliyor. Çözüm selector
kovalamak değil: `CRAFTSBYMAN_KANAL_GIRISI.bat` artık yayıncının kullandığı sayfayı
açıyor, insan turu bir kez elle geçiyor, otomasyon olgun bir hesap görüyor.

**Kalan yapısal iş:** platform state'i iki yerde tutuluyor — `progress.json` ve
`13_PUBLISHING/PUB-*.md`. İkincisi "mevcut kanıt her zaman kazanır" dediği için
birincisinin temizliği tutmuyor. Şu an çelişki raporlanıyor ama tek kaynağa
indirilmedi. Bir müşteride bu olursa kimse elle teşhis edemez.

## Disk

`workspace/` 1.1 GB (segmentler 641 MB, downloads 385 MB) — CLAUDE.md bunları korumayı
şart koşuyor, silme. `screenshots/` 138 MB / 251 dosya; 231'i 15–19 Ağu'dan, kapanmış
olaylara ait — operatör onay verirse temizlenebilir.

## Kurallar (CLAUDE.md)

- Uzak içerik **asla** otomatik silinmez/değiştirilmez.
- Kural 31: UI aksiyonu başına en fazla 2 semantik selector; `force`/JS click/hash class yok.
  DOM gerekiyorsa ve kanıttan çıkarılamıyorsa `NEEDS_USER_HTML`.
- Aynı anda tek pytest, onarım başına en fazla 2 çalıştırma.
- Canlı çalıştırma (Flow/yayın) sadece açık talimatla.
- Reel ID değişmezliği: slot = state = kayıt = dosya adı. Uyuşmazsa `REEL_ID_MEDIA_MISMATCH`.
