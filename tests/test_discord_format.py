from kickminer.config import DiscordConfig
from kickminer.notifiers import base
from kickminer.notifiers.discord import DiscordNotifier
from kickminer.utils import millify


def test_millify():
    assert millify(950) == "950"
    assert millify(1234) == "1.23k"
    assert millify(1000000) == "1M"
    assert millify(0) == "0"
    assert millify(-1500) == "-1.5k"


def test_streamer_repr():
    assert (
        base.streamer_repr("die_schlager_camper", 9623471, 10)
        == "Streamer(username=die_schlager_camper, channel_id=9623471, channel_points=10)"
    )
    assert (
        base.streamer_repr("gaules", 668, 1240000)
        == "Streamer(username=gaules, channel_id=668, channel_points=1.24M)"
    )


SNAP = {"name": "gaules", "channel_id": 668, "points": 220}


def _cap(monkeypatch, n):
    out = []
    monkeypatch.setattr(n, "_send", lambda msg, kind: out.append((msg, kind)))
    n._q.queue.clear()
    return out


def test_discord_twitch_wording_in_embed(monkeypatch):
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=1))
    out = _cap(monkeypatch, n)

    n.status_change("Main", SNAP, "online")
    n.status_change("Main", SNAP, "offline")
    n.points_gain("Main", SNAP, 220, 230)
    n.bonus_claim("Main", SNAP)
    import time

    time.sleep(0.3)
    n.close()
    assert out == [
        ("🥳  Streamer(username=gaules, channel_id=668, channel_points=220) is Online!", "online"),
        ("😴  Streamer(username=gaules, channel_id=668, channel_points=220) is Offline!", "offline"),
        ("🚀  +10 → Streamer(username=gaules, channel_id=668, channel_points=230) - Reason: WATCH.", "gain"),
        ("🎁  Claiming the bonus for Streamer(username=gaules, channel_id=668, channel_points=220)!", "claim"),
    ]
    # the embed carries the coloured border
    p = n._payload("x", "online")
    assert p["embeds"][0]["color"] == 0x53FC18
    p = n._payload("x", "offline")
    assert p["embeds"][0]["color"] == 0x8B8FA3


def test_discord_respects_min_points_gain(monkeypatch):
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=10))
    out = _cap(monkeypatch, n)
    n.points_gain("Main", SNAP, 100, 105)  # +5 suppressed
    n.points_gain("Main", SNAP, 100, 130)  # +30 sent
    import time

    time.sleep(0.3)
    n.close()
    assert [m for m, _ in out] == [
        "🚀  +30 → Streamer(username=gaules, channel_id=668, channel_points=130) - Reason: WATCH."
    ]


def test_discord_startup_shutdown(monkeypatch):
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url="https://x/y"))
    out = _cap(monkeypatch, n)
    n.startup([{"alias": "a", "streamer_order": ["x", "y"]}, {"alias": "b", "streamer_order": ["y"]}])
    n.shutdown("user stopped")
    import time

    time.sleep(0.3)
    n.close()
    assert out == [
        ("🟢  Kick Channel Points Miner started - 2 account(s), 2 streamers.", "start"),
        ("🔴  Kick Channel Points Miner stopped - user stopped.", "stop"),
    ]
