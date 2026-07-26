"""Integration test for Capslock state poller."""
import itertools
import unittest
import threading
import time
from unittest.mock import patch, MagicMock
import capture


class TestCapsLockPoller(unittest.TestCase):
    def setUp(self):
        """Mock the send function and reset state."""
        capture._send_fn = MagicMock()
        capture._focus = capture.FOCUS_PC
        capture._last_pc_capslock_state = False

    def tearDown(self):
        """Stop any running threads."""
        # Threads are daemons, they'll stop when test ends
        pass

    @patch('capture._get_pc_capslock_state')
    def test_capslock_poller_updates_state_while_in_pc_mode(self, mock_get_state):
        """While in PC focus, GetKeyState is reliable (listener unsuppressed)
        - the poller should catch up _last_pc_capslock_state from it. It
        never calls _send_fn itself: forwarding to Amiga only happens via
        _on_key_press or _resync_capslock_to_amiga, never from the poller."""
        # _capslock_poller_loop is an infinite loop with no stop hook, so the
        # background thread outlives this test - the side_effect must never
        # run out or it raises StopIteration in that orphaned thread.
        mock_get_state.side_effect = itertools.chain([False, True], itertools.repeat(True))

        poller_thread = threading.Thread(
            target=capture._capslock_poller_loop,
            daemon=True
        )
        poller_thread.start()

        time.sleep(0.6)

        self.assertTrue(capture._last_pc_capslock_state)
        capture._send_fn.assert_not_called()

    @patch('capture._get_pc_capslock_state')
    def test_capslock_poller_is_noop_during_amiga_focus(self, mock_get_state):
        """Regression: while focus is Amiga, the keyboard listener runs
        suppressed (see _do_set_focus), so Windows never updates GetKeyState's
        toggle bit - it's stale/unreliable there. The poller must not act on
        it at all, or it clobbers the interactive on_press/on_release
        toggle's correct value (previously observed live: pressing Capslock
        while already in Amiga focus toggled ON, then ~200ms later the
        poller "corrected" it back OFF because GetKeyState never changed)."""
        capture._focus = capture.FOCUS_AMIGA
        capture._last_pc_capslock_state = True  # set by the interactive toggle
        # GetKeyState disagrees (stale/never updated because of suppression) -
        # the poller must not "fix" this while focus is Amiga.
        mock_get_state.return_value = False

        poller_thread = threading.Thread(
            target=capture._capslock_poller_loop,
            daemon=True
        )
        poller_thread.start()

        time.sleep(0.6)

        self.assertTrue(capture._last_pc_capslock_state,
                         "Poller must not overwrite state set by the interactive toggle "
                         "while focus is Amiga")
        capture._send_fn.assert_not_called()

    def test_resync_sends_current_state_after_focus_switch(self):
        """Regression: Capslock already ON before switching focus to Amiga
        must still reach the Amiga. The poller only fires on state *changes*,
        so without an explicit resync on focus entry, a pre-existing ON state
        would never be sent."""
        capture._last_pc_capslock_state = True  # Capslock was already ON in PC mode

        capture._resync_capslock_to_amiga()

        capture._send_fn.assert_called_once_with(
            capture.pack_key(0x62, True, capture._qual())
        )

    def test_resync_sends_off_state_too(self):
        """Also verify the OFF case isn't silently skipped."""
        capture._last_pc_capslock_state = False

        capture._resync_capslock_to_amiga()

        capture._send_fn.assert_called_once_with(
            capture.pack_key(0x62, False, capture._qual())
        )


class TestCapslockInteractiveToggle(unittest.TestCase):
    """_on_key_press/_on_key_release must toggle Capslock directly from the
    raw key event, not just via _capslock_poller_loop's GetKeyState polling.

    Regression: while focus is on Amiga, the keyboard listener runs with
    suppress=True (see _do_set_focus), which blocks the event before Windows
    updates its own toggle-state bit - GetKeyState never changes, so the
    poller alone can never detect a Capslock press made while already
    focused on Amiga. See capture.py's _on_key_press comment."""

    def setUp(self):
        capture._send_fn = MagicMock()
        capture._last_pc_capslock_state = False
        capture._capslock_key_held = False

    def test_press_while_amiga_focus_toggles_and_sends(self):
        capture._focus = capture.FOCUS_AMIGA

        capture._on_key_press(capture.Key.caps_lock)

        self.assertTrue(capture._last_pc_capslock_state)
        capture._send_fn.assert_called_once_with(
            capture.pack_key(0x62, True, capture._qual())
        )

    def test_press_while_pc_focus_toggles_but_does_not_send(self):
        capture._focus = capture.FOCUS_PC

        capture._on_key_press(capture.Key.caps_lock)

        self.assertTrue(capture._last_pc_capslock_state)
        capture._send_fn.assert_not_called()

    def test_os_key_repeat_does_not_double_toggle(self):
        """Holding the key down fires on_press repeatedly (OS auto-repeat) -
        only the first DOWN since the last UP may flip the state."""
        capture._focus = capture.FOCUS_AMIGA

        capture._on_key_press(capture.Key.caps_lock)
        capture._on_key_press(capture.Key.caps_lock)
        capture._on_key_press(capture.Key.caps_lock)

        self.assertTrue(capture._last_pc_capslock_state)  # still just one toggle
        self.assertEqual(capture._send_fn.call_count, 1)

    def test_release_then_press_again_toggles_back(self):
        capture._focus = capture.FOCUS_AMIGA

        capture._on_key_press(capture.Key.caps_lock)    # ON
        capture._on_key_release(capture.Key.caps_lock)
        capture._on_key_press(capture.Key.caps_lock)    # OFF

        self.assertFalse(capture._last_pc_capslock_state)
        self.assertEqual(capture._send_fn.call_count, 2)
        capture._send_fn.assert_called_with(
            capture.pack_key(0x62, False, capture._qual())
        )


if __name__ == '__main__':
    unittest.main()
