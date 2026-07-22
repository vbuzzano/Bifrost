import main as bifrost_main


def test_disconnected_when_no_connection_regardless_of_cx():
    assert bifrost_main._systray_state(False, False) == 'disconnected'
    assert bifrost_main._systray_state(False, True) == 'disconnected'


def test_disabled_when_connected_and_cx_disabled():
    assert bifrost_main._systray_state(True, True) == 'disabled'


def test_connected_when_connected_and_cx_enabled():
    assert bifrost_main._systray_state(True, False) == 'connected'
