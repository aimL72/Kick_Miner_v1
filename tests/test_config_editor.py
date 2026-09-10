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
            {"Accounts": [{"alias": "M", "token": "403837437|WPplzqAAAABBBBCCCCDddd", "streamers": ["x"]}]}
        ),
        encoding="utf-8",
    )
    hint = read_editable(p)["accounts"][0]["token_hint"]
    assert hint == "403837437|…Dddd"
    assert "WPplzq" not in hint


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
