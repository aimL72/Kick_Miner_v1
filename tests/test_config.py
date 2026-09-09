import json

import pytest

from kickminer.config import ConfigError, load_config


def _write(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.json")


def test_invalid_json(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_no_usable_accounts(tmp_path):
    p = _write(tmp_path, {"Accounts": [{"alias": "x", "token": "", "streamers": []}]})
    with pytest.raises(ConfigError):
        load_config(p)


def test_multi_account_basic(tmp_path):
    p = _write(
        tmp_path,
        {
            "Language": "de",
            "Accounts": [
                {
                    "alias": "Main",
                    "token": "123|abc",
                    "streamers": ["Foo", "@bar", "bar", "baz"],
                    "max_concurrent": 3,
                }
            ],
        },
    )
    cfg = load_config(p)
    assert cfg.language == "de"
    assert len(cfg.accounts) == 1
    acc = cfg.accounts[0]
    assert acc.streamers == ["foo", "bar", "baz"]  # lowercased, @stripped, deduped
    assert acc.max_concurrent == 3
    assert cfg.total_streamers == 3


def test_legacy_migration(tmp_path):
    p = _write(
        tmp_path,
        {
            "Private": {"token": "999|zzz"},
            "Streamers": ["alice", "bob"],
            "Max_active_channels": 4,
        },
    )
    cfg = load_config(p)
    assert len(cfg.accounts) == 1
    assert cfg.accounts[0].alias == "Default"
    assert cfg.accounts[0].token == "999|zzz"
    assert cfg.accounts[0].max_concurrent == 4


def test_global_proxy_applied_when_account_has_none(tmp_path):
    p = _write(
        tmp_path,
        {
            "Proxy": {"enabled": True, "url": "socks5://h:1"},
            "Accounts": [
                {"alias": "A", "token": "t", "streamers": ["s"], "proxy": None},
                {
                    "alias": "B",
                    "token": "t",
                    "streamers": ["s"],
                    "proxy": "socks5://own:2",
                },
            ],
        },
    )
    cfg = load_config(p)
    assert cfg.accounts[0].proxy == "socks5://h:1"
    assert cfg.accounts[1].proxy == "socks5://own:2"


def test_max_concurrent_floor(tmp_path):
    p = _write(
        tmp_path,
        {"Accounts": [{"alias": "A", "token": "t", "streamers": ["s"], "max_concurrent": 0}]},
    )
    cfg = load_config(p)
    assert cfg.accounts[0].max_concurrent == 1
