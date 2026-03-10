"""
Core proxy rotation engine.

Provides thread-safe round-robin and random proxy selection with
automatic health checking and failure tracking.
"""

import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


class ProxyRotator:
    """Thread-safe proxy rotator with health checking and failure tracking.

    Args:
        proxies: List of proxy URLs (http://, https://, socks5://).
        max_failures: Number of consecutive failures before a proxy is
            automatically removed from the active pool.
        health_check_url: URL used when running ``health_check()``.
        health_check_timeout: Timeout in seconds for each health-check request.
    """

    SUPPORTED_SCHEMES = {"http", "https", "socks5", "socks5h"}

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        max_failures: int = 5,
        health_check_url: str = "https://httpbin.org/ip",
        health_check_timeout: int = 10,
    ) -> None:
        self._lock = threading.Lock()
        self._proxies: List[str] = []
        self._index: int = 0
        self._failures: Dict[str, int] = {}
        self.max_failures = max_failures
        self.health_check_url = health_check_url
        self.health_check_timeout = health_check_timeout

        for proxy in proxies or []:
            self.add_proxy(proxy)

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str, **kwargs) -> "ProxyRotator":
        """Create a ``ProxyRotator`` from a text file (one proxy URL per line).

        Blank lines and lines starting with ``#`` are ignored.
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Proxy file not found: {path}")

        proxies: List[str] = []
        for line in file_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)

        return cls(proxies=proxies, **kwargs)

    # ------------------------------------------------------------------
    # Proxy pool management
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_proxy(url: str) -> str:
        """Validate and normalise a proxy URL."""
        parsed = urlparse(url)
        if parsed.scheme not in ProxyRotator.SUPPORTED_SCHEMES:
            raise ValueError(
                f"Unsupported proxy scheme '{parsed.scheme}'. "
                f"Supported: {', '.join(sorted(ProxyRotator.SUPPORTED_SCHEMES))}"
            )
        if not parsed.hostname:
            raise ValueError(f"Missing hostname in proxy URL: {url}")
        return url

    def add_proxy(self, url: str) -> None:
        """Add a proxy to the active pool.

        Raises ``ValueError`` if the URL scheme is not supported.
        """
        url = self._validate_proxy(url)
        with self._lock:
            if url not in self._proxies:
                self._proxies.append(url)
                self._failures[url] = 0

    def remove_proxy(self, url: str) -> None:
        """Remove a proxy from the pool."""
        with self._lock:
            if url in self._proxies:
                self._proxies.remove(url)
                self._failures.pop(url, None)
                # Keep index in bounds
                if self._proxies and self._index >= len(self._proxies):
                    self._index = 0

    @property
    def active_count(self) -> int:
        """Number of proxies currently in the pool."""
        with self._lock:
            return len(self._proxies)

    @property
    def proxies(self) -> List[str]:
        """Return a snapshot of the current proxy list."""
        with self._lock:
            return list(self._proxies)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def get_next(self) -> str:
        """Return the next proxy using round-robin rotation.

        Raises ``RuntimeError`` if the pool is empty.
        """
        with self._lock:
            if not self._proxies:
                raise RuntimeError("No proxies available in the pool.")
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index = (self._index + 1) % len(self._proxies)
            return proxy

    def get_random(self) -> str:
        """Return a randomly selected proxy.

        Raises ``RuntimeError`` if the pool is empty.
        """
        with self._lock:
            if not self._proxies:
                raise RuntimeError("No proxies available in the pool.")
            return random.choice(self._proxies)

    def get_dict(self, proxy: Optional[str] = None) -> Dict[str, str]:
        """Return a ``requests``-compatible proxy dict.

        If *proxy* is ``None``, the next round-robin proxy is used.

        Example return value::

            {"http": "http://proxy:8080", "https": "http://proxy:8080"}
        """
        if proxy is None:
            proxy = self.get_next()

        parsed = urlparse(proxy)
        scheme = parsed.scheme

        if scheme in ("socks5", "socks5h"):
            return {"http": proxy, "https": proxy}
        return {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------
    # Failure tracking
    # ------------------------------------------------------------------

    def report_failure(self, url: str) -> None:
        """Record a failure for *url*.

        If the failure count reaches ``max_failures`` the proxy is removed
        from the pool automatically.
        """
        with self._lock:
            if url not in self._failures:
                return
            self._failures[url] += 1
            if self._failures[url] >= self.max_failures:
                if url in self._proxies:
                    self._proxies.remove(url)
                    self._failures.pop(url, None)
                    if self._proxies and self._index >= len(self._proxies):
                        self._index = 0

    def report_success(self, url: str) -> None:
        """Reset the failure counter for *url* back to zero."""
        with self._lock:
            if url in self._failures:
                self._failures[url] = 0

    def get_failure_count(self, url: str) -> int:
        """Return the current consecutive failure count for *url*."""
        with self._lock:
            return self._failures.get(url, 0)

    # ------------------------------------------------------------------
    # Health checking
    # ------------------------------------------------------------------

    def _check_single(self, proxy: str) -> bool:
        """Send a test request through *proxy* and return True if it succeeds."""
        proxy_dict = self.get_dict(proxy)
        try:
            resp = requests.get(
                self.health_check_url,
                proxies=proxy_dict,
                timeout=self.health_check_timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def health_check(self, max_workers: int = 10) -> Dict[str, bool]:
        """Test every proxy in the pool concurrently.

        Returns a dict mapping proxy URL to ``True`` (healthy) or
        ``False`` (unhealthy). Unhealthy proxies have their failure
        counters incremented; healthy proxies have counters reset.

        Args:
            max_workers: Maximum number of threads for concurrent checks.
        """
        proxies_snapshot = self.proxies  # thread-safe copy
        results: Dict[str, bool] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_proxy = {
                pool.submit(self._check_single, p): p for p in proxies_snapshot
            }
            for future in as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                try:
                    healthy = future.result()
                except Exception:
                    healthy = False

                results[proxy] = healthy
                if healthy:
                    self.report_success(proxy)
                else:
                    self.report_failure(proxy)

        return results

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self.active_count

    def __repr__(self) -> str:
        return f"ProxyRotator(active={self.active_count}, max_failures={self.max_failures})"

    def __iter__(self):
        """Iterate over proxies infinitely using round-robin."""
        while True:
            yield self.get_next()
