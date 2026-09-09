import asyncio
import threading

from kickminer.http_client import KickHttpClient, safe_get


def test_safe_get_dict_path():
    data = {"data": {"user": {"points": 42}}}
    assert safe_get(data, "data", "user", "points") == 42


def test_safe_get_missing_returns_none():
    assert safe_get({"a": 1}, "b", "c") is None
    assert safe_get(None, "a") is None
    assert safe_get(123, "a") is None


def test_safe_get_list_index():
    data = {"items": [{"id": 1}, {"id": 2}]}
    assert safe_get(data, "items", 1, "id") == 2
    assert safe_get(data, "items", 5, "id") is None
    assert safe_get(data, "items", -1, "id") == 2


def test_safe_get_wrong_type_hop():
    assert safe_get({"a": "string"}, "a", "b") is None


def test_run_executes_on_one_dedicated_thread():
    c = KickHttpClient()
    seen = set()

    def whoami():
        seen.add(threading.current_thread().name)
        return threading.current_thread().name

    async def go():
        for _ in range(6):
            await c.run(whoami)

    asyncio.run(go())
    c.close()
    assert len(seen) == 1
    assert next(iter(seen)).startswith("kickhttp-")


def test_each_client_gets_its_own_thread():
    a, b = KickHttpClient(), KickHttpClient()

    async def name_of(client):
        return await client.run(lambda: threading.current_thread().name)

    na = asyncio.run(name_of(a))
    nb = asyncio.run(name_of(b))
    a.close()
    b.close()
    assert na != nb
