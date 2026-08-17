"""
Instagram web scheduling REHEARSAL.

Walks the whole instagram.com composer flow against the real site -- open composer,
attach the video, advance the steps, write the caption, switch on the AI label and the
schedule toggle, set date and time -- and then STOPS. The final "Planla" button is never
clicked, so nothing is scheduled and nothing is posted.

Why a rehearsal rather than a real run: this week's 14 Reels are already queued on
Instagram through the API/cloud-worker path, so scheduling them again here would publish
every video twice.

    python -m automation.publishing.instagram_web_dry_test
    python -m automation.publishing.instagram_web_dry_test --week-id 2026-W34 --index 1
"""
import argparse
import datetime
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ReelsAIFactory.InstagramWebDryTest")

from automation.orchestration.batch_manifest import BatchRepository
from automation.publishing.instagram_web_browser import InstagramWebBrowserManager
from automation.publishing.instagram_web_observer import InstagramWebObserver


def _step(n: int, text: str) -> None:
    print(f"  [{n}] {text}")


def run_rehearsal(week_id: str, index: int, base_dir: Path) -> int:
    repo = BatchRepository(base_dir)
    manifest = repo.load_manifest(week_id)
    if manifest is None:
        print(f"HATA: {week_id} manifest bulunamadi.")
        return 1

    reel = next((r for r in manifest.reels if r.index == index), None)
    if reel is None:
        print(f"HATA: {week_id} icinde index={index} Reel yok.")
        return 1

    video = Path(reel.video_path) if reel.video_path else None
    if not video or not video.exists():
        print(f"HATA: video dosyasi yok: {video}")
        return 1

    target = datetime.datetime.strptime(reel.scheduled_at_local, "%Y-%m-%d %H:%M:%S")

    print("=" * 62)
    print("INSTAGRAM WEB PROVA -- 'Planla' butonuna BASILMAYACAK")
    print("=" * 62)
    print(f"Reel   : {reel.reel_id}")
    print(f"Video  : {video.name}")
    print(f"Slot   : {reel.scheduled_at_local}")
    print(f"Baslik : {reel.title[:60]}")
    print("=" * 62)

    if InstagramWebObserver.is_slot_too_soon(target):
        print()
        print("NOT: Bu slot su andan 20 dk'dan yakin, Instagram reddeder.")
        print("     Prova yine de calisir; sadece son adimda uyari gorunur.")

    mgr = InstagramWebBrowserManager()
    with mgr.connect() as (_browser, context):
        page = context.pages[0] if context.pages else context.new_page()
        obs = InstagramWebObserver(page)

        try:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"HATA: instagram.com acilamadi: {e}")
            return 1

        results = []

        _step(1, "Composer aciliyor...")
        ok = obs.open_composer()
        results.append(("Composer acildi", ok))

        _step(2, f"Video yukleniyor: {video.name}")
        ok = obs.upload_file(video)
        results.append(("Video eklendi", ok))

        _step(3, "'Ileri' adimlari geciliyor...")
        ok = obs.advance_to_caption_step()
        results.append(("Caption adimina ulasildi", ok))

        _step(4, "Caption yaziliyor...")
        ok = obs.fill_caption(reel.caption, reel.hashtags)
        results.append(("Caption yazildi", ok))

        _step(5, "'Yapay zeka etiketi' aciliyor...")
        ok = obs.enable_ai_label()
        results.append(("AI etiketi acildi", ok))

        _step(6, "'Icerigi planla' aciliyor...")
        ok = obs.enable_schedule()
        results.append(("Planlama acildi", ok))

        _step(7, f"Tarih seciliyor: {obs.format_tr_date(target)}")
        ok, reason = obs.select_date(target)
        results.append((f"Tarih secildi ({reason})", ok))

        _step(8, f"Saat giriliyor: {target.hour:02d}:{target.minute:02d}")
        ok = obs.set_time(target.hour, target.minute)
        results.append(("Saat dogrulandi", ok))

        _step(9, "Son kontroller (TIKLAMA YOK)...")
        sched_on = obs.is_schedule_enabled()
        too_soon = obs.has_time_too_soon_warning()
        results.append(("Planlama anahtari ACIK", sched_on))
        results.append(("'20 dakika' uyarisi YOK", not too_soon))

        print()
        print("=" * 62)
        print("PROVA SONUCU")
        print("=" * 62)
        for label, good in results:
            print(f"  {'[OK]  ' if good else '[HATA]'} {label}")

        failed = [l for l, g in results if not g]
        print()
        if not failed:
            print("TUM ADIMLAR CALISTI. Web planlama yolu hazir.")
            print("Tarayicidaki formu kontrol et: video, caption, tarih ve saat dogru mu?")
        else:
            print(f"{len(failed)} adim calismadi:")
            for l in failed:
                print(f"  - {l}")
            print("screenshots/errors/ altinda kanit dosyalari birakildi.")

        print()
        print("'Planla' butonuna BASILMADI -- hicbir sey planlanmadi.")
        print("Tarayiciyi kendin kapat (veya formu iptal et).")
        print("=" * 62)

        return 0 if not failed else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Instagram web planlama provasi (Planla'ya basmaz)")
    parser.add_argument("--week-id", default="2026-W34")
    parser.add_argument("--index", type=int, default=1, help="Manifest icindeki Reel sirasi (1-14)")
    args = parser.parse_args()
    sys.exit(run_rehearsal(args.week_id, args.index, Path(".").resolve()))


if __name__ == "__main__":
    main()
