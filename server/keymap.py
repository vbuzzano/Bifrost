"""
Bifrost keymap - PC key (pynput) -> Amiga rawkey code mapping.

Amiga rawkey codes for US keyboard layout.
All mapping is done on the server side so the Amiga client stays simple.
"""
from pynput.keyboard import Key

# PC key (pynput Key enum or single char string) -> Amiga rawkey code
AMIGA_RAWKEY: dict = {
    # Top row: ` 1 2 3 4 5 6 7 8 9 0 - =
    '`': 0x00, '1': 0x01, '2': 0x02, '3': 0x03, '4': 0x04,
    '5': 0x05, '6': 0x06, '7': 0x07, '8': 0x08, '9': 0x09,
    '0': 0x0A, '-': 0x0B, '=': 0x0C, '\\': 0x0D,
    # QWERTY row
    'q': 0x10, 'w': 0x11, 'e': 0x12, 'r': 0x13, 't': 0x14,
    'y': 0x15, 'u': 0x16, 'i': 0x17, 'o': 0x18, 'p': 0x19,
    '[': 0x1A, ']': 0x1B,
    # ASDF row
    'a': 0x20, 's': 0x21, 'd': 0x22, 'f': 0x23, 'g': 0x24,
    'h': 0x25, 'j': 0x26, 'k': 0x27, 'l': 0x28,
    ';': 0x29, "'": 0x2A,
    # ZXCV row
    'z': 0x31, 'x': 0x32, 'c': 0x33, 'v': 0x34, 'b': 0x35,
    'n': 0x36, 'm': 0x37, ',': 0x38, '.': 0x39, '/': 0x3A,
    # Space
    ' ': 0x40,
    # --- Special keys via pynput Key enum ---
    Key.space:     0x40,
    Key.backspace: 0x41,
    Key.tab:       0x42,
    Key.enter:     0x44,
    Key.esc:       0x45,
    Key.delete:    0x46,
    # Cursor keys
    Key.up:        0x4C,
    Key.down:      0x4D,
    Key.right:     0x4E,
    Key.left:      0x4F,
    # Function keys
    Key.f1:  0x50, Key.f2:  0x51, Key.f3:  0x52, Key.f4:  0x53,
    Key.f5:  0x54, Key.f6:  0x55, Key.f7:  0x56, Key.f8:  0x57,
    Key.f9:  0x58, Key.f10: 0x59, Key.f11: 0x4B, Key.f12: 0x6F,
    # Modifiers (also injected as key events)
    Key.shift:    0x60, Key.shift_r: 0x61,
    Key.caps_lock: 0x62,
    Key.ctrl_l:   0x63, Key.ctrl:    0x63,
    Key.alt_l:    0x64, Key.alt:     0x64,
    Key.alt_r:    0x65, Key.alt_gr:  0x65,
    # Navigation (mapped to numpad equivalents)
    Key.home:      0x3D,
    Key.end:       0x1D,
    Key.page_up:   0x3F,
    Key.page_down: 0x1F,
    # Amiga keyboards have no PC-style Insert key - PC INS sends Help instead.
    Key.insert:    0x5F,  # Help
    # Left Amiga: fixed to Left Windows (Left Cmd on Mac/Linux), no config.
    Key.cmd:       0x66,  # Left Amiga
}

# Keys that also update the qualifier flags byte
QUAL_MAP: dict = {
    Key.shift:   0x01,  # QUAL_LSHIFT
    Key.shift_r: 0x02,  # QUAL_RSHIFT
    Key.ctrl_l:  0x04,  # QUAL_CTRL
    Key.ctrl:    0x04,
    Key.alt_l:   0x08,  # QUAL_LALT
    Key.alt:     0x08,
    Key.alt_r:   0x10,  # QUAL_RALT
    Key.alt_gr:  0x10,
    # Left Amiga also holds the QUAL_AMIGA qualifier so AmigaOS shortcuts
    # (e.g. Amiga+M) see it as held, not just a raw key press/release.
    Key.cmd:     0x80,  # QUAL_AMIGA
}

# Right Amiga has no single natural PC equivalent across layouts/preference.
# Defaults to Right Windows; set_right_amiga_source(use_ctrl=True) switches
# it to Right Ctrl instead (see keys.right_amiga in bifrost_config.json).
# Both the rawkey code AND the QUAL_AMIGA qualifier move to whichever PC
# key is chosen as the source.
def set_right_amiga_source(use_ctrl: bool) -> None:
    AMIGA_RAWKEY.pop(Key.cmd_r, None)
    AMIGA_RAWKEY.pop(Key.ctrl_r, None)
    QUAL_MAP.pop(Key.cmd_r, None)
    QUAL_MAP.pop(Key.ctrl_r, None)
    source = Key.ctrl_r if use_ctrl else Key.cmd_r
    AMIGA_RAWKEY[source] = 0x67  # Right Amiga
    QUAL_MAP[source] = 0x80      # QUAL_AMIGA

set_right_amiga_source(use_ctrl=False)


def get_rawcode(key) -> 'int | None':
    """Return Amiga rawkey code for a pynput key, or None if unmapped."""
    # Printable char keys
    if hasattr(key, 'char') and key.char:
        return AMIGA_RAWKEY.get(key.char.lower())
    # Special key enum
    return AMIGA_RAWKEY.get(key)
