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


def test_points_message_format(monkeypatch):
    cfg = DiscordConfig(enabled=True, webhook_url="https://x/y", min_points_gain=1)
    from kickminer.notifiers.discord import DiscordNotifier

    n = DiscordNotifier(cfg)
    captured = []
    monkeypatch.setattr(n, "_send", captured.append)
    n._q.queue.clear()
    n.points_gain("Main", "gaules", 220, 230)
    import time

    time.sleep(0.2)
    n.close()
    assert captured == ["`+10 -> gaules (230 points) - Reason: WATCH.`"]
