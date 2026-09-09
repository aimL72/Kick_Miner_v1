from kickminer.account_worker import select_active
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
