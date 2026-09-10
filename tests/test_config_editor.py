import json

import pytest

from kickminer.config_editor import ConfigEditError, apply_action, read_editable


def _cfg(tmp_path, streamers=("a", "b", "c"), limit=2):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "Language": "en",
                "Accounts": [
                    {
                        "alias": "Main",
                        "token": "t",
                        "streamers": list(streamers),
                        "max_concurrent": limit,
                    }
                ],
                "Check_interval": 120,
            }
        ),
        encoding="utf-8",
    )
    return p


def test_read_editable(tmp_path):
    p = _cfg(tmp_path)
    ed = read_editable(p)
    assert ed["accounts"][0]["alias"] == "Main"
    assert ed["accounts"][0]["streamers"] == ["a", "b", "c"]
    assert ed["accounts"][0]["max_concurrent"] == 2
    # token is never returned in full, only a hint
    assert ed["accounts"][0]["has_token"] is True
    assert "token" not in ed["accounts"][0]


def test_read_editable_masks_real_token(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {"Accounts": [{"alias": "M", "token": "12345678|SECRETsecretSECRETsecret", "streamers": ["x"]}]}
        ),
        encoding="utf-8",
    )
    hint = read_editable(p)["accounts"][0]["token_hint"]
    assert hint == "12345678|…cret"
    assert "SECRETsecret" not in hint


def test_set_token(tmp_path):
    p = _cfg(tmp_path)
    apply_action(p, {"action": "set_token", "account": "Main", "token": "999|abcdefghij0123456789"})
    assert json.loads(p.read_text())["Accounts"][0]["token"] == "999|abcdefghij0123456789"
    # other keys survive
    assert json.loads(p.read_text())["Accounts"][0]["streamers"] == ["a", "b", "c"]
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_token", "account": "Main", "token": "not-a-token"})


def test_add_and_remove(tmp_path):
    p = _cfg(tmp_path)
    apply_action(p, {"action": "add", "account": "Main", "streamer": "XQC"})
    assert read_editable(p)["accounts"][0]["streamers"] == ["a", "b", "c", "xqc"]
    apply_action(p, {"action": "remove", "account": "Main", "streamer": "b"})
    assert read_editable(p)["accounts"][0]["streamers"] == ["a", "c", "xqc"]
    # other config keys survive
    assert json.loads(p.read_text())["Check_interval"] == 120


def test_add_rejects_duplicate_and_bad_name(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "add", "account": "Main", "streamer": "a"})
    for bad in ("bad name!", "foo/bar", "../etc", "x" * 42, "-lead", "trail-", "a..b"):
        with pytest.raises(ConfigEditError):
            apply_action(p, {"action": "add", "account": "Main", "streamer": bad})


def test_add_accepts_hyphen_dot_and_longer_names(tmp_path):
    p = _cfg(tmp_path)
    for good in ("los-ratones", "some.channel", "a_very_long_channel_name_1234567890"):
        apply_action(p, {"action": "add", "account": "Main", "streamer": good})
    got = read_editable(p)["accounts"][0]["streamers"]
    assert "los-ratones" in got and "some.channel" in got


def test_reorder(tmp_path):
    p = _cfg(tmp_path)
    apply_action(p, {"action": "reorder", "account": "Main", "streamers": ["c", "a", "b"]})
    assert read_editable(p)["accounts"][0]["streamers"] == ["c", "a", "b"]


def test_reorder_must_be_permutation(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "reorder", "account": "Main", "streamers": ["c", "a"]})


def test_set_limit(tmp_path):
    p = _cfg(tmp_path)
    apply_action(p, {"action": "set_limit", "account": "Main", "max_concurrent": 5})
    assert read_editable(p)["accounts"][0]["max_concurrent"] == 5
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_limit", "account": "Main", "max_concurrent": 0})


def test_unknown_account_and_action(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "add", "account": "Nope", "streamer": "x"})
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "explode", "account": "Main"})


def test_add_account(tmp_path):
    p = _cfg(tmp_path)
    out = apply_action(
        p, {"action": "add_account", "alias": "Alt", "token": "22|abcdefghij0123456789"}
    )
    assert [a["alias"] for a in out["accounts"]] == ["Main", "Alt"]
    alt = out["accounts"][1]
    assert alt["streamers"] == [] and alt["max_concurrent"] == 2
    assert json.loads(p.read_text())["Check_interval"] == 120  # untouched


def test_add_account_rejects_dupe_and_bad_token(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "add_account", "alias": "Main", "token": "22|abcdefghij0123456789"})
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "add_account", "alias": "Alt", "token": "nope"})
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "add_account", "alias": "", "token": "22|abcdefghij0123456789"})


def test_remove_account(tmp_path):
    p = _cfg(tmp_path)
    apply_action(p, {"action": "add_account", "alias": "Alt", "token": "22|abcdefghij0123456789"})
    out = apply_action(p, {"action": "remove_account", "account": "Main"})
    assert [a["alias"] for a in out["accounts"]] == ["Alt"]


def test_remove_last_account_refused(tmp_path):
    p = _cfg(tmp_path)
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "remove_account", "account": "Main"})


def test_read_editable_notifications_masked(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "Accounts": [{"alias": "M", "token": "1|aaaaaaaaaaaaaaaaaaaa", "streamers": ["x"]}],
        "Telegram": {"enabled": True, "bot_token": "123456789:AAbcdefghabcdefghabcdefghabcdefghXYZ", "chat_id": "999"},
        "Discord": {"enabled": True, "webhook_url": "https://discord.com/api/webhooks/111/longsecrettokenvalue0000", "min_points_gain": 5},
    }), encoding="utf-8")
    ed = read_editable(p)
    assert ed["telegram"]["enabled"] is True
    assert ed["telegram"]["chat_id"] == "999"
    assert ed["telegram"]["has_token"] is True
    assert "AAbcdefgh" not in ed["telegram"]["token_hint"]
    assert len(ed["telegram"]["token_hint"]) <= 8
    assert ed["discord"]["min_points_gain"] == 5
    assert ed["discord"]["has_webhook"] is True
    assert "longsecrettokenvalue" not in ed["discord"]["webhook_hint"]
    assert "bot_token" not in ed["telegram"] and "webhook_url" not in ed["discord"]


def _base_cfg(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"Accounts": [{"alias": "M", "token": "1|aaaaaaaaaaaaaaaaaaaa", "streamers": ["x"]}]}), encoding="utf-8")
    return p


def test_set_telegram(tmp_path):
    p = _base_cfg(tmp_path)
    tok = "123456789:AAbcdefghabcdefghabcdefghabcdefghXYZ"
    apply_action(p, {"action": "set_telegram", "enabled": True, "bot_token": tok,
                     "chat_id": "42", "min_points_gain": 20, "notify_points": False})
    raw = json.loads(p.read_text())["Telegram"]
    assert raw["enabled"] is True and raw["bot_token"] == tok
    assert raw["chat_id"] == "42"
    assert raw["min_points_gain"] == 20 and raw["notify_points"] is False
    # toggle off without re-sending the token keeps it
    apply_action(p, {"action": "set_telegram", "enabled": False, "bot_token": ""})
    assert json.loads(p.read_text())["Telegram"]["bot_token"] == tok
    assert json.loads(p.read_text())["Telegram"]["enabled"] is False
    # editable view exposes the flags, not the secret
    ed = read_editable(p)["telegram"]
    assert ed["min_points_gain"] == 20 and ed["notify_points"] is False
    assert "allowed_users" not in ed


def test_set_telegram_rejects_bad_token_and_enable_without_token(tmp_path):
    p = _base_cfg(tmp_path)
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_telegram", "enabled": True, "bot_token": "nope"})
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_telegram", "enabled": True, "bot_token": ""})


def test_set_discord(tmp_path):
    p = _base_cfg(tmp_path)
    hook = "https://discord.com/api/webhooks/1/abcdef"
    apply_action(p, {"action": "set_discord", "enabled": True, "webhook_url": hook,
                     "min_points_gain": 3, "notify_startup": False})
    dc = json.loads(p.read_text())["Discord"]
    assert dc["enabled"] and dc["webhook_url"] == hook
    assert dc["min_points_gain"] == 3 and dc["notify_startup"] is False
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_discord", "enabled": True, "webhook_url": "http://evil.com/x"})


def test_read_editable_cycle_defaults(tmp_path):
    p = _base_cfg(tmp_path)
    assert read_editable(p)["cycle"] == {"enabled": False, "interval_minutes": 15}


def test_set_cycle(tmp_path):
    p = _base_cfg(tmp_path)
    apply_action(p, {"action": "set_cycle", "enabled": True, "interval_minutes": 12})
    cy = json.loads(p.read_text())["Cycle"]
    assert cy == {"enabled": True, "interval_minutes": 12}
    assert read_editable(p)["cycle"]["enabled"] is True
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_cycle", "enabled": True, "interval_minutes": 2})
    with pytest.raises(ConfigEditError):
        apply_action(p, {"action": "set_cycle", "enabled": True, "interval_minutes": 999})
