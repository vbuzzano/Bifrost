import edge_resistance as er


def test_opposite_straight_edges():
    assert er.opposite(er.EDGE_LEFT) == er.EDGE_RIGHT
    assert er.opposite(er.EDGE_RIGHT) == er.EDGE_LEFT
    assert er.opposite(er.EDGE_TOP) == er.EDGE_BOTTOM
    assert er.opposite(er.EDGE_BOTTOM) == er.EDGE_TOP


def test_opposite_corners():
    topleft = er.EDGE_TOP | er.EDGE_LEFT
    bottomright = er.EDGE_BOTTOM | er.EDGE_RIGHT
    assert er.opposite(topleft) == bottomright
    assert er.opposite(bottomright) == topleft


def test_disabled_mask_never_fires():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    for _ in range(20):
        clock[0] += 0.2
        fired = r.update(x=0, y=300, dx=-10, dy=0, w=1000, h=1000, edge_mask=er.EDGE_NONE)
        assert fired is False


def test_straight_edge_fires_after_resistance_and_push():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT

    # Enter the zone (x=0, at the left edge) -> STARTED
    assert r.update(x=0, y=300, dx=-3, dy=0, w=1000, h=1000, edge_mask=mask) is False

    # Still inside the resistance window -> no fire yet
    clock[0] += 0.05
    assert r.update(x=0, y=300, dx=-3, dy=0, w=1000, h=1000, edge_mask=mask) is False

    # Resistance window elapsed (>= PUSH_TIMEOUT_S) -> ACTIVE, next call may fire
    clock[0] += er.PUSH_TIMEOUT_S
    assert r.update(x=0, y=300, dx=-3, dy=0, w=1000, h=1000, edge_mask=mask) is False  # this call just transitions to ACTIVE

    fired = r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA), dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired is True


def test_insufficient_push_delta_does_not_fire():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT

    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)  # -> ACTIVE

    fired = r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA - 1), dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired is False


def test_wrong_direction_push_does_not_fire():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT

    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)  # -> ACTIVE

    # Pushing right (away from the left edge) must never fire
    fired = r.update(x=0, y=300, dx=er.MIN_PUSH_DELTA + 5, dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired is False


def test_leaving_zone_resets_state():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT

    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)  # STARTED
    clock[0] += 0.01
    # Move far away from the edge -> resets to NONE
    r.update(x=500, y=300, dx=500, dy=0, w=1000, h=1000, edge_mask=mask)

    # Immediately back at the edge and pushing hard: must NOT fire yet
    # (resistance window has not been re-served since the reset)
    fired = r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA + 10), dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired is False


def test_cooldown_suppresses_immediate_refire():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT

    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)  # -> ACTIVE
    fired = r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA), dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired is True

    # Immediately pushing again, still in the zone: cooldown suppresses it
    fired_again = r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA), dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired_again is False


def test_refire_after_cooldown_expires():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT

    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)  # -> ACTIVE
    assert r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA), dy=0, w=1000, h=1000, edge_mask=mask) is True

    clock[0] += er.COOLDOWN_S + 0.01
    r.update(x=0, y=300, dx=-1, dy=0, w=1000, h=1000, edge_mask=mask)  # cooldown expired -> ACTIVE again
    fired = r.update(x=0, y=300, dx=-(er.MIN_PUSH_DELTA), dy=0, w=1000, h=1000, edge_mask=mask)
    assert fired is True


def test_corner_fires_on_clean_diagonal_push():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_TOP | er.EDGE_LEFT

    # Enter the corner zone -> STARTED
    r.update(x=0, y=0, dx=-3, dy=-3, w=1000, h=1000, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=0, dx=-3, dy=-3, w=1000, h=1000, edge_mask=mask)  # -> ACTIVE

    # Clean diagonal push (both axes coherent, both >= MIN_PUSH_DELTA) fires
    fired = r.update(x=0, y=0, dx=-(er.MIN_PUSH_DELTA), dy=-(er.MIN_PUSH_DELTA),
                      w=1000, h=1000, edge_mask=mask)
    assert fired is True


def test_corner_does_not_fire_on_ambiguous_single_axis_push():
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_TOP | er.EDGE_LEFT

    r.update(x=0, y=0, dx=-3, dy=0, w=1000, h=1000, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=0, dx=-3, dy=0, w=1000, h=1000, edge_mask=mask)  # -> ACTIVE

    # Push coherent on X only (dx < 0) but dy != 0 (not exactly 0) at a corner:
    # per _push_delta's is_corner branch, "push_h and not push_v" requires
    # abs_dy == 0 exactly to fire. A nonzero dy here (even if not itself a
    # coherent push direction) makes the H-only case return 0 - must not fire.
    fired = r.update(x=0, y=0, dx=-(er.MIN_PUSH_DELTA), dy=2,
                      w=1000, h=1000, edge_mask=mask)
    assert fired is False


def test_corner_mask_does_not_fire_from_the_opposite_corner_sharing_one_edge():
    """Regression: a corner mask like TOPLEFT was firing from ANY point
    along the left edge OR the top edge - including the bottom-left and
    top-right corners, which share exactly one axis with TOPLEFT but are
    not the TOPLEFT corner itself. Reported by real-world testing: running
    with TOPLEFT triggered from the PC's bottom-left corner too."""
    clock = [0.0]
    mask = er.EDGE_TOP | er.EDGE_LEFT   # TOPLEFT
    w, h = 1000, 1000

    for label, x, y, dx, dy in [
        ("bottom-left (shares LEFT only)", 0, h - 1, 0, er.MIN_PUSH_DELTA),
        ("top-right (shares TOP only)", w - 1, 0, er.MIN_PUSH_DELTA, 0),
    ]:
        r = er.EdgeResistance(clock=lambda: clock[0])
        clock[0] = 0.0
        r.update(x=x, y=y, dx=dx, dy=dy, w=w, h=h, edge_mask=mask)
        clock[0] += er.PUSH_TIMEOUT_S + 0.01
        r.update(x=x, y=y, dx=dx, dy=dy, w=w, h=h, edge_mask=mask)  # would-be -> ACTIVE
        fired = r.update(x=x, y=y, dx=dx, dy=dy, w=w, h=h, edge_mask=mask)
        assert fired is False, f"corner mask TOPLEFT incorrectly fired from {label}"


def test_straight_edge_mask_still_fires_anywhere_along_that_edge():
    """Non-regression: a plain single-edge mask (not a corner) must keep
    firing from any point along that edge, not just its midpoint."""
    clock = [0.0]
    r = er.EdgeResistance(clock=lambda: clock[0])
    mask = er.EDGE_LEFT
    w, h = 1000, 1000

    # Near the bottom of the screen, still on the left edge
    r.update(x=0, y=h - 1, dx=-1, dy=0, w=w, h=h, edge_mask=mask)
    clock[0] += er.PUSH_TIMEOUT_S + 0.01
    r.update(x=0, y=h - 1, dx=-1, dy=0, w=w, h=h, edge_mask=mask)  # -> ACTIVE
    fired = r.update(x=0, y=h - 1, dx=-(er.MIN_PUSH_DELTA), dy=0, w=w, h=h, edge_mask=mask)
    assert fired is True


def test_percent_along_edge_straight_edges():
    # w=h=256 chosen so percent maps are exact integers (denominator 255)
    assert er.percent_along_edge(x=0, y=0, w=256, h=256, edge_mask=er.EDGE_LEFT) == 0
    assert er.percent_along_edge(x=0, y=255, w=256, h=256, edge_mask=er.EDGE_LEFT) == 255
    assert er.percent_along_edge(x=0, y=128, w=256, h=256, edge_mask=er.EDGE_LEFT) == 128
    assert er.percent_along_edge(x=64, y=0, w=256, h=256, edge_mask=er.EDGE_TOP) == 64
    assert er.percent_along_edge(x=255, y=200, w=256, h=256, edge_mask=er.EDGE_RIGHT) == 200
    assert er.percent_along_edge(x=100, y=255, w=256, h=256, edge_mask=er.EDGE_BOTTOM) == 100


def test_percent_along_edge_corner_is_always_zero():
    assert er.percent_along_edge(x=0, y=0, w=256, h=256, edge_mask=er.EDGE_TOP | er.EDGE_LEFT) == 0
    assert er.percent_along_edge(x=255, y=255, w=256, h=256, edge_mask=er.EDGE_BOTTOM | er.EDGE_RIGHT) == 0


def test_position_from_percent_straight_edges():
    assert er.position_from_percent(0, 256, 256, er.EDGE_LEFT) == (0, 0)
    assert er.position_from_percent(255, 256, 256, er.EDGE_LEFT) == (0, 255)
    assert er.position_from_percent(128, 256, 256, er.EDGE_LEFT) == (0, 128)
    assert er.position_from_percent(64, 256, 256, er.EDGE_TOP) == (64, 0)
    assert er.position_from_percent(200, 256, 256, er.EDGE_RIGHT) == (255, 200)
    assert er.position_from_percent(100, 256, 256, er.EDGE_BOTTOM) == (100, 255)


def test_position_from_percent_corner_ignores_percent():
    for percent in (0, 1, 128, 254, 255):
        assert er.position_from_percent(percent, 256, 256, er.EDGE_TOP | er.EDGE_LEFT) == (0, 0)
        assert er.position_from_percent(percent, 256, 256, er.EDGE_BOTTOM | er.EDGE_RIGHT) == (255, 255)


def test_percent_round_trip_across_different_resolutions():
    # PC exits near the middle of its left edge; Amiga (much lower
    # resolution) should enter near the middle of its mirrored right edge.
    pc_w, pc_h = 2560, 1440
    amiga_w, amiga_h = 640, 512

    percent = er.percent_along_edge(x=0, y=pc_h // 2, w=pc_w, h=pc_h, edge_mask=er.EDGE_LEFT)
    amiga_edge = er.opposite(er.EDGE_LEFT)  # RIGHT
    x, y = er.position_from_percent(percent, amiga_w, amiga_h, amiga_edge)

    assert x == amiga_w - 1
    # within ~1% of the Amiga screen height of the true midpoint
    assert abs(y - amiga_h // 2) <= amiga_h // 100 + 2
