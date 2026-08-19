"""
Selectors for Instagram's WEB scheduling flow (instagram.com create-post dialog).

Instagram's Graph API has no scheduled-publish parameter, but the web UI does expose
native scheduling ("İçeriği planla" -> date + time -> "Planla"), which lands the post in
instagram.com/scheduled_content/ exactly like YouTube Studio and TikTok Studio do.

Every selector here is SEMANTIC -- visible text, aria-label, or role. Instagram's class
names are hashed atomic CSS ("x1i10hfl xjqpnuy xc5r6h4 ...") that change between builds,
so per Kural 31 they are never used as anchors. All selectors were derived from the real
DOM the operator captured on 2026-08-17.

Kural 31: at most 2 strategies per UI action; each entry below is one strategy, with its
TR/EN variants comma-grouped so Playwright still treats it as a single query.
"""
from typing import List


class InstagramWebSelectors:
    """Semantic selectors for the instagram.com scheduling flow."""

    # Entry point is /scheduled_content/'s own "İçeriği planla" button -- and only that.
    # The generic "Oluştur" composer (sidebar) opens a different dialog with no schedule
    # toggle at all, so it is deliberately NOT a fallback here: falling back to it would
    # silently swap in the wrong flow instead of failing loudly (Kural 31).
    OPEN_COMPOSER_BUTTONS: List[str] = [
        "div[role='button']:has-text('İçeriği planla'), div[role='button']:has-text('Schedule content')",
    ]

    # "Fotoğrafları ve videoları buraya sürükle" -> <button>Bilgisayardan seç</button>
    SELECT_FROM_COMPUTER_BUTTONS: List[str] = [
        "button:has-text('Bilgisayardan seç'), button:has-text('Select from computer')",
        "div[role='dialog'] button:has-text('Bilgisayardan'), div[role='dialog'] button:has-text('computer')",
    ]

    FILE_INPUTS: List[str] = [
        "div[role='dialog'] input[type='file']",
        "input[type='file'][accept*='video'], input[type='file']",
    ]

    # Crop screen -> filter screen -> caption screen. Same "İleri" control each time.
    NEXT_BUTTONS: List[str] = [
        "div[role='button']:has-text('İleri'), div[role='button']:has-text('Next')",
        "div[role='dialog'] div[role='button']:text-is('İleri'), div[role='dialog'] div[role='button']:text-is('Next')",
    ]

    CAPTION_INPUTS: List[str] = [
        "div[role='dialog'] textarea[aria-label*='başlık' i], div[role='dialog'] textarea[aria-label*='caption' i]",
        "div[role='dialog'] div[contenteditable='true'], div[role='dialog'] textarea",
    ]

    # --- Toggles -----------------------------------------------------------
    # Both render as: <div>...<span>LABEL</span>... <input role="switch" aria-checked="..">
    # so the switch is located by walking from its label text to the nearest switch input.
    AI_LABEL_TOGGLE_TEXTS: List[str] = [
        "Yapay zeka etiketi ekle",
        "Add AI label",
    ]

    SCHEDULE_TOGGLE_TEXTS: List[str] = [
        "İçeriği planla",
        "Schedule content",
    ]

    SWITCH_INPUTS: List[str] = [
        "input[role='switch']",
    ]

    # --- Date / time -------------------------------------------------------
    # Date opens a dialog: <div aria-haspopup="dialog" role="button"><span>17 Ağu 2026 Pzt</span>
    DATE_PICKER_BUTTONS: List[str] = [
        "div[role='button'][aria-haspopup='dialog']",
    ]

    # Time is two spinbuttons with stable English aria-labels even in the Turkish UI.
    HOUR_INPUTS: List[str] = [
        "input[aria-label='Hours'], input[aria-label='Saat']",
    ]

    MINUTE_INPUTS: List[str] = [
        "input[aria-label='Minutes'], input[aria-label='Dakika']",
    ]

    # --- Final action ------------------------------------------------------
    # Top-right "Planla" on the composer. This SCHEDULES; it is not an immediate share.
    SCHEDULE_SUBMIT_BUTTONS: List[str] = [
        "div[role='button']:text-is('Planla'), div[role='button']:text-is('Schedule')",
        "div[role='dialog'] div[role='button']:has-text('Planla'), div[role='dialog'] div[role='button']:has-text('Schedule')",
    ]

    # Never click these. With the schedule toggle ON the composer's primary action becomes
    # "Planla", but if the toggle failed to engage it stays "Paylaş"/"Share" and would post
    # immediately -- which is why the toggle is verified before the final click.
    FORBIDDEN_IMMEDIATE_SHARE_LABELS: List[str] = [
        "paylaş",
        "share",
        "hemen paylaş",
        "share now",
    ]

    # The success dialog: title "Reels videosu planlandı", body "Reels videon planlandı."
    # (captured 2026-08-19). Both contain the first marker.
    SCHEDULE_SUCCESS_MARKERS: List[str] = [
        "planlandı",
        "scheduled",
        "gönderin planlandı",
    ]

    # Its "Bitti" button: <div role="button" tabindex="0">Bitti</div>, hashed classes only.
    SUCCESS_DIALOG_DONE_BUTTONS: List[str] = [
        "div[role='button']:text-is('Bitti'), div[role='button']:text-is('Done')",
        "div[role='dialog'] div[role='button']:has-text('Bitti'), div[role='dialog'] div[role='button']:has-text('Done')",
    ]

    # Instagram refuses a slot that is too close to now, showing
    # "Şu andan en az 20 dakika sonra olan bir zaman seç" under the time field
    # (captured 2026-08-17 with the time set to 15:30 while the clock read ~15:11).
    # Attempting such a slot silently fails to schedule, so it is pre-checked.
    MIN_LEAD_MINUTES: int = 20

    TIME_TOO_SOON_MARKERS: List[str] = [
        "en az 20 dakika",
        "at least 20 minutes",
    ]

    # The date row is <span>Tarih</span> next to the aria-haspopup button; scoping through
    # the label avoids matching other popup buttons in the composer.
    DATE_ROW_LABELS: List[str] = ["Tarih", "Date"]
    TIME_ROW_LABELS: List[str] = ["Saat", "Time"]

    # --- Date picker dialog (confirmed against the real DOM, 2026-08-17) ---------
    # Structure:
    #   <button aria-label="Previous month" disabled>   (disabled at the current month)
    #   <span>Ağustos 2026</span>                        (month header)
    #   <button aria-label="Next month">
    #   <div role="grid">
    #     <button role="gridcell" aria-disabled="true"  tabindex="-1"><span>26</span>  <- prev month
    #     <button role="gridcell" aria-disabled="false" aria-selected="true"><span>17</span>  <- today
    #     <button role="gridcell" aria-disabled="false"><span>18</span>
    #     <button role="gridcell" aria-disabled="true"><span>1</span>   <- NEXT month
    #
    # The grid deliberately includes trailing days of the previous month and leading days
    # of the next one, all aria-disabled. Matching a day by text alone would therefore hit
    # September 1st when asked for "1", so aria-disabled='false' is part of the selector,
    # not an optimisation. Past days of the current month are disabled the same way.
    MONTH_HEADER: List[str] = [
        "div[role='grid'] >> xpath=preceding-sibling::div[1]//span",
        "span:right-of(button[aria-label='Previous month'])",
    ]

    # Only selectable cells: excludes past days and adjacent-month spillover.
    DAY_CELL_TEMPLATES: List[str] = [
        "button[role='gridcell'][aria-disabled='false']:has(span:text-is('{day}'))",
        "button[role='gridcell'][aria-disabled='false']:text-is('{day}')",
    ]

    SELECTED_DAY_CELL: str = "button[role='gridcell'][aria-selected='true']"

    # aria-label stays English even in the Turkish UI.
    NEXT_MONTH_BUTTONS: List[str] = [
        "button[aria-label='Next month']",
        "button[aria-label*='next month' i], button[aria-label*='sonraki ay' i]",
    ]

    PREV_MONTH_BUTTONS: List[str] = [
        "button[aria-label='Previous month']",
        "button[aria-label*='previous month' i], button[aria-label*='önceki ay' i]",
    ]

    # Header renders the FULL month name ("Ağustos 2026"), unlike the date button's
    # abbreviation ("17 Ağu 2026 Pzt").
    TR_MONTHS_FULL = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
    }
