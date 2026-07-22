"""Tests for capture.py's client state tracking.

Only the deterministic state-flag behavior is covered here - the
focus-forcing side effect (a background thread calling _do_set_focus)
mirrors the already-untested EMERGENCY key handler pattern in the same
file, and isn't re-verified here.
"""
import capture


def test_set_amiga_client_state_enabled_clears_disabled_flag():
    capture._amiga_client_disabled = True
    capture.set_amiga_client_state(True)
    assert capture._amiga_client_disabled is False


def test_set_amiga_client_state_disabled_sets_flag():
    capture._amiga_client_disabled = False
    capture._focus = capture.FOCUS_PC  # avoid spawning a focus-change thread
    capture.set_amiga_client_state(False)
    assert capture._amiga_client_disabled is True


def test_reset_amiga_client_state_clears_flag():
    capture._amiga_client_disabled = True
    capture._reset_amiga_client_state()
    assert capture._amiga_client_disabled is False


def test_set_focus_amiga_refused_while_client_disabled():
    """Regression test: _set_focus() used to only gate FOCUS_AMIGA on
    _connected_fn(), so a manual toggle (e.g. Scroll Lock) could still
    switch back into Amiga mode right after an Exchange Disable forced
    focus back to PC - defeating the whole point of Disable.

    Asserts that no background thread is spawned at all (rather than
    checking capture._focus afterward), since _do_set_focus runs
    asynchronously - checking _focus right after _set_focus() returns
    would race the thread and could pass even on the old, buggy code
    simply because the thread hadn't run yet."""
    spawned = []

    class _FakeThread:
        def __init__(self, *args, **kwargs):
            spawned.append((args, kwargs))
        def start(self):
            pass

    original_thread = capture.threading.Thread
    capture.threading.Thread = _FakeThread
    try:
        capture._connected_fn = lambda: True  # connected, so that check passes
        capture._amiga_client_disabled = True
        capture._focus = capture.FOCUS_PC
        capture._set_focus(capture.FOCUS_AMIGA)
        assert spawned == []  # no thread was ever constructed/started
    finally:
        capture.threading.Thread = original_thread
