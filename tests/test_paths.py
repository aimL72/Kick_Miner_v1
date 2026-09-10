import importlib
import sys


def _reload_paths(monkeypatch, **env):
    for k in ("KICK_MINER_DATA", "KICK_MINER_CONFIG"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("kickminer.paths", None)
    return importlib.import_module("kickminer.paths")


def test_default_is_cwd_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    p = _reload_paths(monkeypatch)
    assert p.CONFIG_PATH == (tmp_path / "config.json")
    assert p.LOG_DIR == (tmp_path / "logs")
    assert p.ANALYTICS_DB == (tmp_path / "data" / "analytics.sqlite3")


def test_data_root_env_roots_everything(monkeypatch, tmp_path):
    root = tmp_path / "vol"
    p = _reload_paths(monkeypatch, KICK_MINER_DATA=str(root))
    assert p.CONFIG_PATH == (root / "config.json")
    assert p.LOG_DIR == (root / "logs")
    assert p.ANALYTICS_DB == (root / "data" / "analytics.sqlite3")


def test_explicit_config_env_wins(monkeypatch, tmp_path):
    p = _reload_paths(
        monkeypatch,
        KICK_MINER_DATA=str(tmp_path),
        KICK_MINER_CONFIG=str(tmp_path / "custom.json"),
    )
    assert p.CONFIG_PATH == (tmp_path / "custom.json")


def teardown_module(module):  # keep other tests seeing the real module
    sys.modules.pop("kickminer.paths", None)
    importlib.import_module("kickminer.paths")
