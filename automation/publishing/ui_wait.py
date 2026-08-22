"""
One place for "is this element there yet?".

Playwright's ``Locator.is_visible(timeout=...)`` ignores its timeout. It is a snapshot of
the current state, not a wait, and returns immediately -- so every call site that passed a
timeout to it was reading a page mid-render and concluding the element did not exist.

That is the single mechanical cause behind a week of "not found" failures across Flow,
YouTube Studio and TikTok Studio: Flow's unloaded workspace, YouTube's content check, the
video id that came back empty for seven Reels, TikTok's date field, and the file input
that stopped a week at its twelfth Reel. Each was patched where it hurt; this is the thing
underneath all of them.

``wait_for(state="visible")`` is the call that actually polls, and raises on timeout
rather than returning a bool -- which is why every conversion needs a wrapper rather than
a rename.
"""
from typing import Any


def visible(locator: Any, timeout_ms: int = 1000) -> bool:
    """
    Whether `locator` is visible, waiting up to `timeout_ms` for it to become so.

    Returns a bool so it can be dropped into the boolean conditions the observers already
    read naturally -- ``if visible(loc, 1500) and loc.is_enabled():``.
    """
    if locator is None:
        return False

    waiter = getattr(locator, "wait_for", None)
    if waiter is None:
        # A stub or test fake that implements only the snapshot check. Falling back to it
        # keeps such objects working; reporting them as missing would be worse than the
        # instant answer they can give.
        checker = getattr(locator, "is_visible", None)
        if checker is None:
            return False
        try:
            return bool(checker())
        except Exception:
            return False

    try:
        waiter(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False
