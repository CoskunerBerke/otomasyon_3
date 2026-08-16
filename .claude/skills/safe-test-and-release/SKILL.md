---
name: safe-test-and-release
description: Bir kod düzeltmesinden sonra test çalıştırma, secret tarama, git diff kontrolü ve commit/push adımlarını CLAUDE.md'deki katı test politikasına göre yürütür. Claude bu projede bir bug düzelttikten, yeni bir test yazdıktan veya değişiklikleri commit/push etmeye hazırlandığında mutlaka bu skill'i kullan. Kullanıcı "test et", "commit at", "push et" dediğinde de bu skill'in adımlarını izle.
---

# Safe Test & Release

## Ne zaman kullanılır

- Bir kod düzeltmesi/özellik tamamlandı ve doğrulanıp commit edilmesi gerekiyor.
- Kullanıcı doğrudan "testleri çalıştır", "commit at", "push et" diyor.
- Başka bir skill (reels-pipeline-doctor, production-media-guardian, vb.) bir düzeltme yaptı ve şimdi güvenli şekilde kapatılması gerekiyor.

## Ne zaman kullanılmaz

- Henüz bir kod değişikliği yok, sadece araştırma/teşhis aşamasındaysa (o zaman ilgili teşhis skill'i kullan, testi en sonda burada çalıştır).
- Kullanıcı açıkça "tüm test suite'ini çalıştır" istemiyorsa, hiçbir zaman kendi inisiyatifinle tam suite çalıştırma.

## Temel kural kaynağı

Bu skill, repository kökündeki **`CLAUDE.md`**'nin "Testing policy for repair/hardening tasks" bölümünü OPERASYONEL bir kontrol listesine çevirir. Kurallar orada tanımlıdır, burada tekrar edilmiyor — çelişki olursa CLAUDE.md geçerlidir. Özet (güncel haliyle CLAUDE.md'yi kontrol et, burası sadece hatırlatma):
- Aynı anda maksimum 1 pytest süreci.
- Bir onarım görevi başına maksimum 2 pytest çağrısı; ikincisi de başarısız/timeout olursa DUR, üçüncüyü çalıştırma.
- İlk çağrı ~60 saniye sınırı hedeflenir; PASS ise tekrar çalıştırma.
- Tam test suite'i sadece kullanıcı açıkça isterse.
- Gerçek tarayıcı, gerçek Flow üretimi, gerçek YouTube/TikTok/Instagram/Telegram çağrısı olan testler yok — sadece mock/fake.

## Görev akışı

1. **Kapsamı belirle.** Sadece değiştirilen/etkilenen dosyalarla ilgili test dosyalarını hedefle (`git diff --stat` veya `git status` ile hangi `automation/` modüllerinin değiştiğine bak, karşılık gelen `tests/test_*.py` dosyalarını seç). Rastgele geniş bir küme çalıştırma.
2. **İlk pytest çağrısı.** Seçilen test dosyalarını tek bir `python -m pytest <dosyalar> -q` komutuyla çalıştır. Sonucu oku:
   - Hepsi geçtiyse → 3. adıma geç, tekrar test ÇALIŞTIRMA.
   - Başarısızlık varsa → başarısızlığın DEĞİŞTİRDİĞİN koddan mı yoksa önceden var olan/ilgisiz bir sorundan mı kaynaklandığını `git diff` ile ayır (örnek yöntem: dokunmadığın bir fonksiyonun testi başarısızsa, o fonksiyonu gerçekten değiştirmediğini diff'te doğrula). İlgisizse, kullanıcıya dürüstçe raporla ve düzeltmeye ÇALIŞMA (kapsam dışı); ilgiliyse tek seferde düzelt.
3. **İkinci (son) pytest çağrısı** — sadece 2. adımda gerçek bir düzeltme yaptıysan. Bu SON denemedir; başarısız olursa dur, üçüncü bir deneme yapma, başarısızlığı olduğu gibi raporla.
4. **Secret scan.** `python -m automation.cloud.secret_scan` çalıştır (repo'nun kendi tarayıcısı — yeniden icat etme). `SECRET_SCAN_PASS` görmeden commit'e geçme.
5. **Git diff gözden geçir.** `git status --porcelain=v1` ve `git diff --stat` ile SADECE beklenen dosyaların değiştiğini doğrula. `.env`, `*.mp4`, secret içerebilecek screenshot, `workspace/` altındaki state dosyaları (zaten `.gitignore`'da) stage edilmemeli.
6. **Stage & commit.** Dosyaları isimleriyle (`git add <dosya1> <dosya2> ...`) stage et, `git add -A`/`git add .` kullanma. Commit mesajı: neden (kök neden) + ne değişti, "what" değil "why" odaklı. `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` satırını ekle.
7. **Push** — kullanıcı bunu istemişse veya görev tanımı açıkça push'u kapsıyorsa `git push origin main`. Force push YOK. Kullanıcı açıkça istemediyse push etme, sadece commit'i bildir.
8. **Türkçe kısa final rapor** üret (aşağıdaki şablon).

## Rapor şablonu

```
- Kök neden: ...
- Değişen dosyalar: ...
- Test sonucu: X geçti / Y kaldı (varsa neden ilgisiz olduğu açıklaması)
- Pytest çağrı sayısı: N (politika: max 2)
- Secret scan: PASS/FAIL
- Git status: temiz / bekleyen değişiklik yok
- Commit SHA: ...
- Push sonucu: yapıldı / yapılmadı (neden)
```

## Güvenlik sınırları

- `--no-verify`, `--no-gpg-sign` gibi hook/imza atlatma bayraklarını asla kullanmaz.
- `git reset --hard`, `git clean -f`, `git push --force` gibi yıkıcı komutları kullanıcı açık onayı olmadan çalıştırmaz.
- Testler için gerçek tarayıcı açmaz, gerçek Flow/platform çağrısı yapmaz.

## İlgili repository dosyaları

`CLAUDE.md` (otoritatif kaynak), `tests/` (tüm test dosyaları), `automation/cloud/secret_scan.py`.

## Başarılı sonuç kriterleri

- Pytest en fazla 2 kez çalıştırılmış, süreç sırası (1 process at a time) korunmuş.
- Secret scan PASS.
- Sadece beklenen dosyalar stage edilmiş.
- Commit mesajı kök nedeni açıklıyor.
- Rapor şablonundaki tüm alanlar dolu ve doğru.
