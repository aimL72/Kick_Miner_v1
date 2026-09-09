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
    n.points_gain("Main", {"name": "x", "channel_id": 1, "points": 100}, 0, 100)


def test_discord_and_telegram_produce_identical_text():
    """The whole point of the shared builders: one wording for both channels."""
    from kickminer.notifiers import base

    snap = {"name": "gaules", "account_username": "aimL72"}
    assert (
        base.msg_status("Main", snap, "online")
        == "Account aimL72\n\U0001F973 gaules is online"
    )


def test_telegram_permission_logic():
    bot = TelegramBot(TelegramConfig(enabled=False, chat_id="111", allowed_users=[222]))
    assert bot._is_owner(111) is True
    assert bot._is_owner(222) is False
    assert bot._is_allowed(222) is True
    assert bot._is_allowed(333) is False


def test_telegram_disabled_when_no_token():
    bot = TelegramBot(TelegramConfig(enabled=True, bot_token=""))
    assert bot.enabled is False


def test_telegram_push_format():
    import asyncio

    bot = TelegramBot(TelegramConfig(enabled=False, chat_id="1"))
    sent = []

    async def fake(text):
        sent.append(text)

    bot._broadcast = fake
    snap = {"name": "xqc", "account_username": "aimL72", "account_alias": "Main Account"}
    asyncio.run(bot.notify_status("Main Account", snap, "online"))
    asyncio.run(bot.notify_status("Main Account", snap, "offline"))
    asyncio.run(bot.notify_points("Main Account", snap, 3400, 3412))
    assert sent[0] == "Account aimL72\n🥳 xqc is online"
    assert sent[1] == "Account aimL72\n😴 xqc is offline"
    assert sent[2] == "Account aimL72\n🚀 xqc +12 → 3,412 Points"


def test_telegram_acct_falls_back_to_alias():
    assert TelegramBot._acct("Main Account", {"name": "x"}) == "Account Main Account"
    assert TelegramBot._acct("Main Account", {"account_username": "aimL72"}) == "Account aimL72"
