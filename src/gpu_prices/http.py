from __future__ import annotations

import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_USER_AGENT = (
    "gpu-price-monitor/0.1 (https://github.com/DanielWang2029/GPU-Price-Mining)"
)


class FetchError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, *, timeout: float = 30, allow_read_proxy: bool = False):
        self.timeout = timeout
        self.allow_read_proxy = allow_read_proxy
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": os.getenv("GPU_PRICE_USER_AGENT", DEFAULT_USER_AGENT),
                "Accept": "*/*",
            }
        )
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        if not response.ok:
            content_type = response.headers.get("content-type", "")
            body = (
                response.text[:300].replace("\n", " ") if "text" in content_type else ""
            )
            raise FetchError(
                f"{method.upper()} {url} returned HTTP {response.status_code}"
                + (f": {body}" if body else "")
            )
        return response

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.request("GET", url, **kwargs).text

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise FetchError(f"GET {url} did not return JSON") from exc

    def post_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("POST", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise FetchError(f"POST {url} did not return JSON") from exc

    def read_proxy_text(self, url: str) -> tuple[str, str]:
        if not self.allow_read_proxy:
            raise FetchError(
                f"{url} blocked direct collection and the optional public read proxy is disabled"
            )
        proxy_url = f"https://r.jina.ai/{url}"
        return self.get_text(proxy_url), proxy_url
