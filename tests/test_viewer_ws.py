import asyncio

import pytest

from kickminer.viewer_ws import ViewerWebSocket


def _ws(**kw):
    return ViewerWebSocket(
        ws_token="tok-1", channel_id=1, stream_id=2, label="t", **kw
    )


def test_first_connect_flag_and_provider_stored():
    calls = []

    async def provider():
        calls.append(1)
        return "tok-2"

    ws = _ws(token_provider=provider)
    assert ws._first_connect is True
    assert ws.ws_token == "tok-1"


def test_reconnect_refreshes_token(monkeypatch):
    """The 2nd+ connect must pull a fresh viewer WS token (they expire ~15 min)."""

    tokens = iter(["tok-2", "tok-3"])

    async def provider():
        return next(tokens)

    ws = _ws(token_provider=provider)

    # stub out the actual network connect so we only exercise the token path
    async def fake_ws_connect(*a, **k):
        raise RuntimeError("stop before real connect")

    class FakeSession:
        def __init__(self, *a, **k):
            pass

        async def ws_connect(self, *a, **k):
            raise RuntimeError("stop")

        async def close(self):
            pass

    monkeypatch.setattr("kickminer.viewer_ws.AsyncSession", FakeSession)

    # first connect: keeps tok-1, flips the flag
    asyncio.run(ws._connect_once())
    assert ws.ws_token == "tok-1"
    assert ws._first_connect is False

    # second connect: pulls a fresh token from the provider
    asyncio.run(ws._connect_once())
    assert ws.ws_token == "tok-2"

    asyncio.run(ws._connect_once())
    assert ws.ws_token == "tok-3"


def test_no_provider_keeps_token(monkeypatch):
    ws = _ws()

    class FakeSession:
        def __init__(self, *a, **k):
            pass

        async def ws_connect(self, *a, **k):
            raise RuntimeError("stop")

        async def close(self):
            pass

    monkeypatch.setattr("kickminer.viewer_ws.AsyncSession", FakeSession)
    asyncio.run(ws._connect_once())
    asyncio.run(ws._connect_once())
    assert ws.ws_token == "tok-1"
