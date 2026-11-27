"""A small, polite HTTP client: throttling, retries and 429 back-off.

Both Jolpica and OpenF1 are free community services with rate limits, so
every request goes through :class:`PoliteSession`.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = "f1predict/0.1 (research project; python-requests)"


class PoliteSession:
    def __init__(self, min_interval: float = 0.5, max_retries: int = 6, timeout: float = 60):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT

    def get(self, url: str, params: dict | None = None, **kwargs) -> requests.Response:
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:  # network blip
                log.warning("GET %s failed (%s), retry %d", url, exc, attempt)
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    pause = float(retry_after) if retry_after and retry_after.isdigit() else delay
                    log.warning("GET %s -> %s, sleeping %.0fs", url, resp.status_code, pause)
                    time.sleep(pause)
                else:
                    return resp
            time.sleep(delay)
            delay = min(delay * 2, 120)
        raise RuntimeError(f"GET {url} failed after {self.max_retries} attempts")

    def get_json(self, url: str, params: dict | None = None):
        resp = self.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
