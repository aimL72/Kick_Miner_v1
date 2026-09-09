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


SNAP = {"name": "gaules", "channel_id": 668, "points": 3412, "account_username": "aimL72"}


def test_shared_message_builders():
    assert base.msg_status("Main", SNAP, "online") == "Account aimL72\n🥳 gaules is online"
    assert base.msg_status("Main", SNAP, "offline") == "Account aimL72\n😴 gaules is offline"
    assert (
        base.msg_points("Main", SNAP, 3400, 3412)
        == "Account aimL72\n🚀 gaules +12 → 3,412 Points"
    )
    assert base.account_label("Main Account", {"name": "x"}) == "Account Main Account"


def test_startup_shutdown():
    assert base.msg_startup(
        [{"alias": "a", "streamer_order": ["x", "y"]}, {"alias": "b", "streamer_order": ["y"]}]
    ) == "🟢 Kick Miner started — 2 account(s), 2 streamers"
    assert base.msg_shutdown("user stopped") == "🔴 Kick Miner stopped — user stopped"


def test_discord_sends_embeds_with_shared_text(monkeypatch):
    cfg = DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=1)
    n = DiscordNotifier(cfg)
    captured = []
    monkeypatch.setattr(n, "_send", lambda msg, kind: captured.append((msg, kind)))
    n._q.queue.clear()

    n.status_change("Main", SNAP, "online")
    n.status_change("Main", SNAP, "offline")
    n.points_gain("Main", SNAP, 3400, 3412)
    import time

    time.sleep(0.3)
    n.close()
    assert captured == [
        ("Account aimL72\n🥳 gaules is online", "online"),
        ("Account aimL72\n😴 gaules is offline", "offline"),
        ("Account aimL72\n🚀 gaules +12 → 3,412 Points", "gain"),
    ]
    # embed payload carries the colour border
    p = n._payload("x", "online")
    assert p["embeds"][0]["color"] == 0x53FC18 and p["embeds"][0]["description"] == "x"


def test_discord_respects_min_points_gain(monkeypatch):
    cfg = DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=10)
    n = DiscordNotifier(cfg)
    captured = []
    monkeypatch.setattr(n, "_send", lambda msg, kind: captured.append(msg))
    n._q.queue.clear()
    n.points_gain("Main", SNAP, 100, 105)  # +5, suppressed
    n.points_gain("Main", SNAP, 100, 130)  # +30, sent
    import time

    time.sleep(0.3)
    n.close()
    assert captured == ["Account aimL72\n🚀 gaules +30 → 130 Points"]
