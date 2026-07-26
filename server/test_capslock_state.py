"""Tests for Capslock state polling and synchronization."""
import unittest
from unittest.mock import patch, MagicMock, call
import capture


class TestCapslock(unittest.TestCase):
    def setUp(self):
        """Reset capslock state before each test."""
        capture._last_pc_capslock_state = False
        capture._send_fn = MagicMock()

    @patch('capture._IS_WIN', True)
    @patch('capture.ctypes')
    def test_get_pc_capslock_state_on(self, mock_ctypes):
        """Test that GetKeyState returns True when Capslock is ON."""
        mock_ctypes.windll.user32.GetKeyState.return_value = 1  # bit 0 set = ON
        result = capture._get_pc_capslock_state()
        self.assertTrue(result)
        mock_ctypes.windll.user32.GetKeyState.assert_called_with(0x14)

    @patch('capture._IS_WIN', True)
    @patch('capture.ctypes')
    def test_get_pc_capslock_state_off(self, mock_ctypes):
        """Test that GetKeyState returns False when Capslock is OFF."""
        mock_ctypes.windll.user32.GetKeyState.return_value = 0  # bit 0 clear = OFF
        result = capture._get_pc_capslock_state()
        self.assertFalse(result)

    @patch('capture._IS_WIN', False)
    def test_get_pc_capslock_state_non_windows(self):
        """Test that non-Windows always returns False."""
        result = capture._get_pc_capslock_state()
        self.assertFalse(result)

    @patch('capture.pack_key')
    @patch('capture.LOG_KEYS', False)
    def test_send_capslock_event_pressed(self, mock_pack_key):
        """Test sending a Capslock press event."""
        mock_pack_key.return_value = b'\x03\x00\x00\x00\x62\x01'  # PKT_KEY pressed
        capture._send_fn = MagicMock()

        capture._send_capslock_event(True)

        # Verify pack_key was called with code=0x62, pressed=True
        mock_pack_key.assert_called_once()
        args = mock_pack_key.call_args[0]
        self.assertEqual(args[0], 0x62)  # Capslock rawkey
        self.assertEqual(args[1], True)   # pressed=True
        capture._send_fn.assert_called_once()

    @patch('capture.pack_key')
    @patch('capture.LOG_KEYS', False)
    def test_send_capslock_event_released(self, mock_pack_key):
        """Test sending a Capslock release event."""
        mock_pack_key.return_value = b'\x03\x00\x00\x00\x62\x00'  # PKT_KEY released
        capture._send_fn = MagicMock()

        capture._send_capslock_event(False)

        args = mock_pack_key.call_args[0]
        self.assertEqual(args[0], 0x62)
        self.assertEqual(args[1], False)  # pressed=False


if __name__ == '__main__':
    unittest.main()
