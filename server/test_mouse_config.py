"""Tests for Amiga-owned mouse-tuning config (capture.apply_amiga_config)."""
import unittest
from unittest.mock import patch, MagicMock
import capture
from protocol import PKT_HELLO


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


if __name__ == '__main__':
    unittest.main()
