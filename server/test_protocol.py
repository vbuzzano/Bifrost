import protocol


def test_pack_focus_enter_byte_layout():
    data = protocol.pack_focus_enter(0x80)
    assert data == bytes([protocol.PKT_FOCUS_ENTER, 0, 0, 0, 0, 0, 0x80, 0])
    assert len(data) == 8


def test_pack_edge_trigger_with_percent():
    data = protocol.pack_edge_trigger(0x40)
    assert data == bytes([protocol.PKT_EDGE_TRIGGER, 0, 0, 0, 0, 0, 0x40, 0])
    assert len(data) == 8


def test_pack_edge_trigger_default_percent_is_zero():
    data = protocol.pack_edge_trigger()
    assert data == bytes([protocol.PKT_EDGE_TRIGGER, 0, 0, 0, 0, 0, 0, 0])


def test_focus_enter_packet_type_value_matches_design():
    # Must stay in sync with src/daemon.c PKT_FOCUS_ENTER
    assert protocol.PKT_FOCUS_ENTER == 0x07


def test_pack_hello_byte_layout():
    data = protocol.pack_hello(0x05)
    assert len(data) == 8
    assert data == bytes([protocol.PKT_HELLO, 0, 0, 0, 0, 0, 0x05, 0])


def test_pack_hello_disabled():
    data = protocol.pack_hello(0)
    assert len(data) == 8
    assert data[0] == protocol.PKT_HELLO
    assert data[6] == 0


def test_pack_edge_trigger_byte_layout():
    data = protocol.pack_edge_trigger()
    assert len(data) == 8
    assert data == bytes([protocol.PKT_EDGE_TRIGGER, 0, 0, 0, 0, 0, 0, 0])


def test_packet_type_values_match_design():
    # Must stay in sync with src/daemon.c PKT_HELLO / PKT_EDGE_TRIGGER
    assert protocol.PKT_HELLO == 0x05
    assert protocol.PKT_EDGE_TRIGGER == 0x06


def test_pack_client_state_enabled():
    data = protocol.pack_client_state(True)
    assert data == bytes([protocol.PKT_CLIENT_STATE, 0, 0, 0, 0, 0, 1, 0])
    assert len(data) == 8


def test_pack_client_state_disabled():
    data = protocol.pack_client_state(False)
    assert data == bytes([protocol.PKT_CLIENT_STATE, 0, 0, 0, 0, 0, 0, 0])


def test_client_state_packet_type_value_matches_design():
    # Must stay in sync with src/bifrost.h PKT_CLIENT_STATE
    assert protocol.PKT_CLIENT_STATE == 0x08
