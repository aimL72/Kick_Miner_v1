import time

from kickminer.analytics import Analytics


def test_record_and_history(tmp_path):
    a = Analytics(tmp_path / "a.sqlite3")
    a.record("Main", "gaules", 100)
    a.record("Main", "gaules", 110)
    a.record("Main", "xqc", 5)

    hist = a.history("gaules", hours=1)
    assert [r["balance"] for r in hist] == [100, 110]
    assert a.history("xqc", hours=1)[0]["balance"] == 5
    assert set(a.streamers()) == {"gaules", "xqc"}
    a.close()


def test_history_account_filter(tmp_path):
    a = Analytics(tmp_path / "a.sqlite3")
    a.record("Main", "gaules", 1)
    a.record("Alt", "gaules", 2)
    assert len(a.history("gaules", hours=1)) == 2
    assert [r["balance"] for r in a.history("gaules", account="Alt", hours=1)] == [2]
    a.close()


def test_history_time_window(tmp_path):
    a = Analytics(tmp_path / "a.sqlite3")
    old = int(time.time()) - 5 * 3600
    with a._lock:
        a._db.execute(
            "INSERT INTO points_history (ts, account, streamer, balance) VALUES (?,?,?,?)",
            (old, "Main", "gaules", 50),
        )
    a.record("Main", "gaules", 60)
    assert [r["balance"] for r in a.history("gaules", hours=2)] == [60]
    assert len(a.history("gaules", hours=24)) == 2
    a.close()


def test_case_insensitive_streamer(tmp_path):
    a = Analytics(tmp_path / "a.sqlite3")
    a.record("Main", "gaules", 1)
    assert a.history("GAULES", hours=1)[0]["balance"] == 1
    a.close()
