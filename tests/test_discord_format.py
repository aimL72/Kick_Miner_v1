from kickminer.config import DiscordConfig
from kickminer.notifiers.discord import DiscordNotifier
from kickminer.utils import millify


def test_millify():
    assert millify(950) == "950"
    assert millify(1234) == "1.23k"
    assert millify(1000000) == "1M"
    assert millify(-1500) == "-1.5k"


SNAP = {"name": "gaules", "channel_id": 668, "points": 220, "account_username": "aimL72"}


def _cap(monkeypatch, n):
    out = []
    monkeypatch.setattr(n, "_send", lambda msg, kind: out.append((msg, kind)))
    n._q.queue.clear()
    return out


def test_discord_wording_and_colours(monkeypatch):
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=1))
    out = _cap(monkeypatch, n)

    n.status_change("Main", SNAP, "online")
    n.status_change("Main", SNAP, "offline")
    n.points_gain("Main", SNAP, 220, 230)
    n.startup([{"alias": "a", "streamer_order": ["x", "y"]}])
    n.shutdown("whatever")
    import time

    time.sleep(0.3)
    n.close()
    assert out == [
        ("Account aimL72\n🥳 → gaules is online", "online"),
        ("Account aimL72\n😴 → gaules is offline", "offline"),
        ("Account aimL72\n🚀 +10 Points → gaules (230)", "gain"),
        ("🟢 Kick Channelpoints Miner Started", "start"),
        ("🔴 Kick Channelpoints Miner Stopped", "stop"),
    ]
    assert n._payload("x", "online")["embeds"][0]["color"] == 0x53FC18
    assert n._payload("x", "offline")["embeds"][0]["color"] == 0x8B8FA3
    assert n._payload("x", "stop")["embeds"][0]["color"] == 0xF04747


def test_discord_respects_min_points_gain(monkeypatch):
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=10))
    out = _cap(monkeypatch, n)
    n.points_gain("Main", SNAP, 100, 105)  # +5 suppressed
    n.points_gain("Main", SNAP, 100, 130)  # +30 sent
    import time

    time.sleep(0.3)
    n.close()
    assert [m for m, _ in out] == ["Account aimL72\n🚀 +30 Points → gaules (130)"]


def test_discord_thousands_separator(monkeypatch):
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=1))
    out = _cap(monkeypatch, n)
    n.points_gain("Main", SNAP, 3400, 4412)
    import time

    time.sleep(0.3)
    n.close()
    assert out[0][0] == "Account aimL72\n🚀 +1,012 Points → gaules (4,412)"
