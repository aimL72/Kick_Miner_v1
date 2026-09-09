from kickminer.config import DiscordConfig
from kickminer.notifiers.discord import _fence
from kickminer.utils import millify


def test_millify():
    assert millify(950) == "950"
    assert millify(1234) == "1.23k"
    assert millify(1000000) == "1M"
    assert millify(0) == "0"
    assert millify(-1500) == "-1.5k"


def test_fence_oneliner():
    assert _fence("gaules (230 points) is Online!") == "`gaules (230 points) is Online!`"


def test_fence_multiline_uses_triple_backticks():
    out = _fence("line one\nline two")
    assert out.startswith("```\n") and out.endswith("\n```")


def test_fence_escapes_existing_backticks():
    out = _fence("a `code` b")
    assert out == "`` a `code` b ``"


def test_streamer_repr_and_messages(monkeypatch):
    from kickminer.notifiers.discord import DiscordNotifier

    cfg = DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=1)
    n = DiscordNotifier(cfg)
    captured = []
    monkeypatch.setattr(n, "_send", captured.append)
    n._q.queue.clear()

    snap = {"name": "gaules", "channel_id": 668, "points": 246720}
    n.points_gain("Main", snap, 246708, 246720)
    n.status_change("Main", snap, "online")
    n.status_change("Main", snap, "offline")
    n.bonus_claim("Main", snap)
    import time

    time.sleep(0.3)
    n.close()
    assert captured == [
        "`🚀  +12 → Streamer(username=gaules, channel_id=668, channel_points=246.72k) - Reason: WATCH.`",
        "`🥳  Streamer(username=gaules, channel_id=668, channel_points=246.72k) is Online!`",
        "`😴  Streamer(username=gaules, channel_id=668, channel_points=246.72k) is Offline!`",
        "`🎁  Claiming the bonus for Streamer(username=gaules, channel_id=668, channel_points=246.72k)!`",
    ]
