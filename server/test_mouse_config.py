"""Tests for Amiga-owned mouse-tuning config (capture.apply_amiga_config)."""
import unittest
from unittest.mock import patch, MagicMock
import capture
from protocol import PKT_HELLO, QUAL_LBUTTON, QUAL_RBUTTON


def _hello_bytes(edge=0, hz=50, hz_drag=15, delta_max=80, speed=10,
                  curve_linear=20, curve_ratio=5):
    return bytes([PKT_HELLO, hz, hz_drag, delta_max, speed, curve_linear, edge, curve_ratio])


class TestApplyAmigaConfig(unittest.TestCase):
    def setUp(self):
        capture._mouse_timer_started = False
        capture.MOUSE_HZ = None
        capture.MOUSE_HZ_DRAG = None
        capture.MOUSE_SPEED = None
        capture.DELTA_MAX = None
        capture.CURVE_LINEAR = None
        capture.CURVE_RATIO = None
        capture.MOUSE_INTERVAL = None
        capture._pc_edge_mask = capture.EDGE_NONE

    @patch('capture.threading.Thread')
    def test_apply_amiga_config_sets_all_values(self, mock_thread_cls):
        capture.apply_amiga_config(_hello_bytes(
            edge=0x05, hz=75, hz_drag=20, delta_max=60,
            speed=15, curve_linear=40, curve_ratio=8))

        self.assertEqual(capture._pc_edge_mask, 0x05)
        self.assertEqual(capture.MOUSE_HZ, 75)
        self.assertEqual(capture.MOUSE_HZ_DRAG, 20)
        self.assertEqual(capture.DELTA_MAX, 60)
        self.assertEqual(capture.MOUSE_SPEED, 1.5)
        self.assertEqual(capture.CURVE_LINEAR, 4.0)
        self.assertEqual(capture.CURVE_RATIO, 0.8)
        self.assertAlmostEqual(capture.MOUSE_INTERVAL, 1.0 / 75)

    @patch('capture.threading.Thread')
    def test_apply_amiga_config_starts_timer_thread_on_first_call(self, mock_thread_cls):
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        capture.apply_amiga_config(_hello_bytes())

        mock_thread_cls.assert_called_once_with(target=capture._mouse_timer_loop, daemon=True)
        mock_thread_instance.start.assert_called_once()
        self.assertTrue(capture._mouse_timer_started)

    @patch('capture.threading.Thread')
    def test_apply_amiga_config_does_not_restart_timer_on_second_call(self, mock_thread_cls):
        capture.apply_amiga_config(_hello_bytes(hz=50))
        mock_thread_cls.reset_mock()

        capture.apply_amiga_config(_hello_bytes(hz=75))  # live re-send, changed value

        mock_thread_cls.assert_not_called()
        self.assertEqual(capture.MOUSE_HZ, 75)  # value still updates in place


class TestResetAmigaConfig(unittest.TestCase):
    def setUp(self):
        capture._pc_edge_mask = 0x05

    def test_reset_clears_edge_only(self):
        capture.MOUSE_HZ = 75  # simulate an already-running timer thread's value

        capture.reset_amiga_config()

        self.assertEqual(capture._pc_edge_mask, capture.EDGE_NONE)
        self.assertEqual(capture.MOUSE_HZ, 75)  # untouched - see reset_amiga_config()'s docstring


class TestOnMoveAmigaRecenter(unittest.TestCase):
    """Regression: on non-Windows, _on_move_amiga used to track the real
    cursor position with no re-centering ("SetCursorPos is unreliable, no
    warp needed"). A gesture that entered Amiga focus at a screen edge (e.g.
    x=0) then had nowhere further to go in that direction - the real cursor
    clamped at the edge, silently zeroing every further delta that way for
    as long as the push continued. Real-world report: edge-triggered entry
    on Linux, then moving the mouse further left did nothing.

    Re-centering only actually happens near a screen edge (_RECENTER_MARGIN)
    - warping on every single event was a real X11 round trip each time and
    was visibly janky/stuttery in real-world testing."""

    def setUp(self):
        capture.DELTA_MAX = 80
        capture._last_x = None
        capture._last_y = None
        capture._acc_dx = 0
        capture._acc_dy = 0
        capture._qualifiers = 0
        capture._mouse_btns = 0

    @patch('capture._recenter_cursor_fast')
    def test_recenters_when_near_an_edge(self, mock_recenter):
        edge_x = capture._RECENTER_MARGIN - 3   # inside the margin, near the left edge
        # First call only seeds _last (no prior tracked position yet)
        capture._on_move_amiga(edge_x, 500)
        mock_recenter.assert_not_called()

        # Real move, e.g. continuing left from a left-edge entry point
        capture._on_move_amiga(edge_x - 2, 500)

        self.assertEqual(capture._acc_dx, -2)
        self.assertEqual(capture._acc_dy, 0)
        # Warped back to center instead of being left wherever the real
        # (edge-adjacent) cursor position was
        mock_recenter.assert_called_once_with(capture._center_x, capture._center_y)
        self.assertEqual(capture._last_x, capture._center_x)
        self.assertEqual(capture._last_y, capture._center_y)

    @patch('capture._recenter_cursor_fast')
    def test_does_not_warp_when_nowhere_near_an_edge(self, mock_recenter):
        # Comfortably inside the screen, far from any edge
        capture._on_move_amiga(capture._center_x, capture._center_y)
        capture._on_move_amiga(capture._center_x - 2, capture._center_y)

        self.assertEqual(capture._acc_dx, -2)
        mock_recenter.assert_not_called()
        # _last tracks the real position, not a warp target, when no warp happened
        self.assertEqual(capture._last_x, capture._center_x - 2)
        self.assertEqual(capture._last_y, capture._center_y)

    @patch('capture._recenter_cursor_fast')
    def test_still_warps_while_dragging_near_an_edge(self, mock_recenter):
        # Regression: the warp used to be skipped entirely while a mouse
        # button was held, to avoid the jank of a blocking X11 round trip
        # mid-drag - which let a drag that ran into a real screen edge get
        # stuck there at dx=0 until release. _recenter_cursor_fast() is
        # non-blocking, so there's no jank tradeoff to avoid anymore, and
        # the warp now fires during a drag same as any other move.
        edge_x = capture._RECENTER_MARGIN - 3
        for held in (QUAL_LBUTTON, QUAL_RBUTTON):
            with self.subTest(held=held):
                capture._last_x = None
                capture._last_y = None
                mock_recenter.reset_mock()
                capture._mouse_btns = held

                capture._on_move_amiga(edge_x, 500)
                capture._on_move_amiga(edge_x - 2, 500)

                mock_recenter.assert_called_once_with(capture._center_x, capture._center_y)
                self.assertEqual(capture._last_x, capture._center_x)
                self.assertEqual(capture._last_y, capture._center_y)

    @patch('capture._recenter_cursor_fast')
    def test_synthetic_warp_echo_does_not_add_a_second_delta(self, mock_recenter):
        edge_x = capture._RECENTER_MARGIN - 3
        capture._on_move_amiga(edge_x, 500)
        capture._on_move_amiga(edge_x - 2, 500)  # real move near the edge -> warps
        capture._acc_dx = 0
        capture._acc_dy = 0

        # The warp's own synthetic on_move event reports the cursor already
        # sitting at the target center position - must not be double-counted
        capture._on_move_amiga(capture._center_x, capture._center_y)

        self.assertEqual(capture._acc_dx, 0)
        self.assertEqual(capture._acc_dy, 0)


if __name__ == '__main__':
    unittest.main()
