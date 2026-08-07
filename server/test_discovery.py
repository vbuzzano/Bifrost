import discovery


def test_build_discover_message_embeds_port():
    assert discovery.build_discover_message(7890) == b'Bifrost_DISCOVER:7890'


def test_build_discover_message_prefix_matches_amiga_side():
    # Must stay in sync with src/bifrost.h DISC_MSG / DISC_MSG_LEN
    data = discovery.build_discover_message(1234)
    assert data[:16] == b'Bifrost_DISCOVER'
    assert data[16:17] == b':'


def test_build_discover_message_different_ports():
    assert discovery.build_discover_message(80) == b'Bifrost_DISCOVER:80'
    assert discovery.build_discover_message(65535) == b'Bifrost_DISCOVER:65535'


def test_disc_port_matches_amiga_side():
    # Must stay in sync with src/bifrost.h Bifrost_DISC_PORT
    assert discovery.DISC_PORT == 7891
