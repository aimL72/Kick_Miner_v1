import time

from kickminer.account_worker import (
    cycle_window,
    eligible_online,
    is_no_points,
    select_active,
)
from kickminer.entities import AccountState, StreamerState


ORDER = ["s0", "s1", "s2", "s3"]


def test_picks_highest_priority_online():
    active = select_active(ORDER, {"s1", "s2", "s3"}, 2)
    assert active == ["s1", "s2"]  # s0 offline, list order preserved


def test_displacement_when_higher_priority_comes_online():
    assert select_active(ORDER, {"s2", "s3"}, 2) == ["s2", "s3"]
    assert select_active(ORDER, {"s0", "s2", "s3"}, 2) == ["s0", "s2"]


def test_limit_zero_and_none_online():
    assert select_active(ORDER, {"s0", "s1"}, 0) == []
    assert select_active(ORDER, set(), 3) == []


def test_fewer_online_than_limit():
    assert select_active(ORDER, {"s3"}, 2) == ["s3"]


def test_ignores_unknown_online_names():
    assert select_active(ORDER, {"ghost", "s1"}, 5) == ["s1"]


def _states(online, cooldown=None):
    cooldown = cooldown or {}
    d = {}
    for i, n in enumerate(ORDER):
        s = StreamerState(name=n, priority=i)
        s.is_online = n in online
        s.cooldown_until = cooldown.get(n, 0.0)
        d[n] = s
    return d


def test_eligible_online_excludes_cooldown():
    now = time.monotonic()
    st = _states({"s0", "s1", "s2"}, cooldown={"s1": now + 300})
    assert eligible_online(ORDER, st, watching=set(), now=now) == {"s0", "s2"}


def test_eligible_online_keeps_watched_despite_cooldown():
    now = time.monotonic()
    st = _states({"s0", "s1"}, cooldown={"s1": now + 300})
    assert eligible_online(ORDER, st, watching={"s1"}, now=now) == {"s0", "s1"}


def test_eligible_online_expired_cooldown():
    now = time.monotonic()
    st = _states({"s0"}, cooldown={"s0": now - 5})
    assert eligible_online(ORDER, st, watching=set(), now=now) == {"s0"}


def test_account_snapshot_shape():
    state = AccountState(alias="A", proxy=None, max_concurrent=2, order=list(ORDER))
    for i, n in enumerate(ORDER):
        state.streamers[n] = StreamerState(name=n, priority=i)
    state.streamers["s0"].is_online = True
    state.streamers["s0"].is_watching = True
    state.streamers["s0"].points = 500
    state.streamers["s0"].points_start = 450

    snap = state.snapshot()
    assert snap["alias"] == "A"
    assert snap["active_count"] == 1
    assert snap["active_streamers"] == ["s0"]
    assert snap["total_points"] == 500
    assert snap["streamers"]["s0"]["points_gained"] == 50




def test_cycle_window_groups_and_rotation():
    order = ["s0", "s1", "s2", "s3", "s4"]
    assert cycle_window(order, 2, 0, 900) == (0, 3, ["s0", "s1"], 900)
    assert cycle_window(order, 2, 950, 900)[:3] == (1, 3, ["s2", "s3"])
    assert cycle_window(order, 2, 1900, 900)[:3] == (2, 3, ["s4"])
    assert cycle_window(order, 2, 2800, 900)[:3] == (0, 3, ["s0", "s1"])  # wrapped


def test_cycle_window_next_switch_countdown():
    _, _, _, nxt = cycle_window(["a", "b", "c"], 1, 300, 900)
    assert nxt == 600  # 300s into a 900s window


def test_cycle_window_single_group():
    assert cycle_window(["a", "b"], 2, 5000, 900) == (0, 1, ["a", "b"], 400)


def test_is_no_points():
    grace = 1800.0  # 30 min
    # flat line past the grace window -> skip
    assert is_no_points(1900, 0, grace) is True
    # not watched long enough yet
    assert is_no_points(1200, 0, grace) is False
    # earned something -> keep
    assert is_no_points(3600, 10, grace) is False
    # feature disabled
    assert is_no_points(9999, 0, 0) is False
    assert is_no_points(9999, 0, -1) is False
