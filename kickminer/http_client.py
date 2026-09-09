"""One HTTP session for all Kick REST traffic.

Kick sits behind Cloudflare, so plain ``requests`` gets a 403. ``curl_cffi``
impersonates a real Chrome TLS/HTTP fingerprint, which is enough to pass.

Replaces the three near-identical session classes of the original Baillora
miner (``KickPoints``, ``KickUtility``, ``PointsAmount``) with a single
reusable client: one bootstrap, one cookie jar, one 403-retry path.
"""

from __future__ import annotations

import asyncio
import itertools
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from curl_cffi import requests
from loguru import logger

_client_seq = itertools.count()

from .i18n import t

# Static token the Kick web frontend sends on some authenticated endpoints
# (e.g. the viewer WebSocket token). Public value, not account-specific.
DEFAULT_CLIENT_TOKEN = (
    "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
)

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://kick.com",
    "Referer": "https://kick.com/",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "X-Requested-With": "XMLHttpRequest",
}


class KickHttpClient:
    """Wrapper around a single ``curl_cffi`` session.

    ``curl_cffi``'s sync ``Session`` is not safe to touch from multiple OS
    threads, even serialized - doing so segfaults the process under load. So
    every request runs on this client's own single worker thread; call the
    async helpers (``a_get`` / ``a_get_json`` / ``a_request``) from the event
    loop, or wrap sync calls with :meth:`run`.
    """

    def __init__(
        self,
        *,
        proxy: str | None = None,
        auth_token: str | None = None,
        impersonate: str = "chrome124",
        client_token: str | None = DEFAULT_CLIENT_TOKEN,
        timeout: int = 15,
    ) -> None:
        self.proxy = proxy
        self.timeout = timeout
        self._auth_token = auth_token
        self._client_token = client_token
        self._lock = threading.Lock()
        self._bootstrapped = False
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"kickhttp-{next(_client_seq)}"
        )

        proxies = {"http": proxy, "https": proxy} if proxy else None
        self._session = requests.Session(impersonate=impersonate, proxies=proxies)
        self._session.headers.update(_BASE_HEADERS)
        if client_token:
            self._session.headers["X-Client-Token"] = client_token
        self._apply_auth()

    # ------------------------------------------------------------------ #
    # setup

    def _apply_auth(self) -> None:
        if self._auth_token:
            self._session.headers["Authorization"] = f"Bearer {self._auth_token}"
        else:
            self._session.headers.pop("Authorization", None)

    def set_auth_token(self, token: str | None) -> None:
        with self._lock:
            self._auth_token = token
            self._apply_auth()

    def _bootstrap(self, *, force: bool = False) -> None:
        """Fetch Cloudflare clearance cookies by loading the base page once."""

        if self._bootstrapped and not force:
            return

        logger.debug(t("http_session_init"))
        try:
            resp = self._session.get("https://kick.com/", timeout=self.timeout)
            status = resp.status_code
            if status == 200:
                logger.debug(t("http_session_ok", status=status))
            elif status == 403:
                logger.warning(t("http_session_403"))
            else:
                logger.warning(t("http_session_bad_status", status=status))

            for name, value in {
                "showMatureContent": "true",
                "USER_LOCALE": "en",
            }.items():
                self._session.cookies.set(name, value, domain="kick.com")

            time.sleep(random.uniform(0.4, 1.2))
        except Exception as exc:  # noqa: BLE001 - network layer, log and continue
            logger.error(t("http_session_error", error=str(exc)))
        finally:
            self._bootstrapped = True

    # ------------------------------------------------------------------ #
    # requests

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        retry_on_403: bool = True,
    ) -> requests.Response | None:
        """Perform a request. Returns ``None`` only on a transport error."""

        with self._lock:
            self._bootstrap()
            try:
                resp = self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=self.timeout,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(t("http_request_failed", url=url, error=str(exc)))
                return None

            if resp.status_code == 403 and retry_on_403:
                logger.warning(t("http_retry_403", url=url))
                self._bootstrap(force=True)
                try:
                    resp = self._session.request(
                        method,
                        url,
                        headers=headers,
                        json=json,
                        params=params,
                        timeout=self.timeout,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        t("http_request_failed", url=url, error=str(exc))
                    )
                    return None

            return resp

    def get(self, url: str, **kwargs: Any) -> requests.Response | None:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response | None:
        return self.request("POST", url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any | None:
        """GET and parse JSON. Returns ``None`` on any failure (logged by caller)."""

        resp = self.get(url, **kwargs)
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except Exception:  # noqa: BLE001 - non-JSON body
            return None

    # ------------------------------------------------------------------ #
    # async wrappers - everything runs on this client's single worker thread

    async def run(self, fn, /, *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    async def a_get(self, url: str, **kwargs: Any) -> requests.Response | None:
        return await self.run(lambda: self.get(url, **kwargs))

    async def a_get_json(self, url: str, **kwargs: Any) -> Any | None:
        return await self.run(lambda: self.get_json(url, **kwargs))

    def close(self) -> None:
        # the curl session must be closed on its owning thread
        try:
            self._executor.submit(self._session.close).result(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        self._executor.shutdown(wait=False, cancel_futures=True)


def safe_get(data: Any, *keys: str | int) -> Any | None:
    """Walk nested dict/list keys without raising. Returns ``None`` if any hop fails."""

    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            current = current[key] if -len(current) <= key < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current
