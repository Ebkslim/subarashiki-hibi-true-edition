"""Polite HTTP client honoring SEC fair-access rules.

SEC requires:
- A User-Agent containing real contact info (name + email).
- A request rate of <= 10 requests/second sustained across sec.gov hosts.

See https://www.sec.gov/os/accessing-edgar-data
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Optional

import requests


_DEFAULT_UA_ENV = "SEC_USER_AGENT"


def _resolve_user_agent(user_agent: Optional[str]) -> str:
    ua = user_agent or os.environ.get(_DEFAULT_UA_ENV, "").strip()
    if not ua:
        raise RuntimeError(
            "SEC requires a User-Agent with contact info. Set the "
            f"{_DEFAULT_UA_ENV} environment variable, e.g.\n"
            f"  export {_DEFAULT_UA_ENV}='Your Name your.email@example.com'"
        )
    if not re.search(r"[\w.+-]+@[\w.-]+\.\w+", ua):
        raise RuntimeError(
            "SEC User-Agent must include a contact email address. Got: "
            + repr(ua)
        )
    return ua


class PoliteClient:
    """Rate-limited, retry-friendly HTTP client."""

    def __init__(
        self,
        user_agent: Optional[str] = None,
        requests_per_sec: float = 8.0,
        max_retries: int = 4,
        backoff_base: float = 1.5,
    ) -> None:
        ua = _resolve_user_agent(user_agent)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate",
        })
        self.min_interval = 1.0 / max(requests_per_sec, 0.5)
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._last_call = 0.0
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def get(
        self,
        url: str,
        *,
        accept: Optional[str] = None,
        stream: bool = False,
        timeout: float = 30.0,
    ) -> requests.Response:
        headers: dict[str, str] = {}
        if accept:
            headers["Accept"] = accept
        attempt = 0
        while True:
            self._throttle()
            try:
                r = self.session.get(
                    url, headers=headers, stream=stream, timeout=timeout
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.backoff_base ** attempt)
                attempt += 1
                continue
            if r.status_code == 429 or 500 <= r.status_code < 600:
                if attempt >= self.max_retries:
                    r.raise_for_status()
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(int(retry_after))
                else:
                    time.sleep(self.backoff_base ** attempt)
                attempt += 1
                continue
            r.raise_for_status()
            return r
