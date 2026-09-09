from kickminer.config import DiscordConfig, TelegramConfig
from kickminer.notifiers.base import format_uptime, summarize_accounts
from kickminer.notifiers.discord import DiscordNotifier
from kickminer.notifiers.telegram import TelegramBot


def test_format_uptime():
    assert format_uptime(30) == "0m"
    assert format_uptime(90) == "1m"
    assert format_uptime(3700) == "1h 1m"
    assert format_uptime(90000) == "1d 1h 0m"


def test_summarize_accounts():
    snap = [
        {
            "alias": "Main",
            "active_count": 1,
            "max_concurrent": 2,
            "uptime_seconds": 3661,
            "total_points": 250,
            "streamer_order": ["a", "b"],
            "streamers": {
                "a": {"priority": 0, "online": True, "watching": True, "points": 200, "points_gained": 50},
                "b": {"priority": 1, "online": False, "watching": False, "points": 50, "points_gained": 0},
            },
        }
    ]
    out = summarize_accounts(snap)
    assert "Main" in out and "1h 1m" in out
    assert "a — 200 (+50)" in out
    assert "b — 50" in out
    assert "250 points" in out


def test_discord_disabled_without_url():
    n = DiscordNotifier(DiscordConfig(enabled=True, webhook_url=""))
    assert n.enabled is False
    n.points_gain("Main", "x", 0, 100)  # must not raise


def test_discord_enqueues_only_above_threshold(monkeypatch):
    cfg = DiscordConfig(enabled=True, webhook_url="https://example.com/hook", min_points_gain=10)
    n = DiscordNotifier(cfg)
    # stop the worker thread from actually sending
    sent = []
    monkeypatch.setattr(n, "_send", lambda p: sent.append(p))
    n._q.queue.clear()

    n.points_gain("Main", "x", 100, 105)   # +5, below threshold
    n.points_gain("Main", "x", 100, 130)   # +30, above
    import time
    time.sleep(0.3)
    n.close()
    assert len(sent) == 1
    assert sent[0]["embeds"][0]["title"] == "💰 Points earned"


def test_telegram_permission_logic():
    bot = TelegramBot(TelegramConfig(enabled=False, chat_id="111", allowed_users=[222]))
    assert bot._is_owner(111) is True
    assert bot._is_owner(222) is False
    assert bot._is_allowed(222) is True
    assert bot._is_allowed(333) is False


def test_telegram_disabled_when_no_token():
    bot = TelegramBot(TelegramConfig(enabled=True, bot_token=""))
    assert bot.enabled is False
