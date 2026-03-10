"""
Drop-in replacement for ``requests.Session`` with automatic proxy rotation.

Every outgoing request is routed through the next proxy in the pool.
Failed requests are retried with different proxies up to ``max_retries``
times, with optional exponential backoff.
"""

import time
from typing import Any, List, Optional

import requests
from requests import Response

from .rotator import ProxyRotator


class RotatingSession(requests.Session):
    """A ``requests.Session`` subclass that rotates proxies automatically.

    Args:
        proxies: List of proxy URLs to rotate through.
        max_retries: Maximum number of retry attempts per request.
        backoff_factor: Multiplier for exponential backoff between retries.
            The delay before retry *n* is ``backoff_factor * 2 ** (n - 1)``.
        max_failures: Consecutive failures before a proxy is removed.
        rotator: An existing ``ProxyRotator`` instance. If provided,
            *proxies* and *max_failures* are ignored.
    """

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        max_retries: int = 3,
        backoff_factor: float = 0.3,
        max_failures: int = 5,
        rotator: Optional[ProxyRotator] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.rotator = rotator or ProxyRotator(
            proxies=proxies or [],
            max_failures=max_failures,
        )
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    # ------------------------------------------------------------------
    # Override request dispatch
    # ------------------------------------------------------------------

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        """Send a request, automatically rotating proxies and retrying on failure.

        If a request fails, the proxy's failure counter is incremented and the
        request is retried with the next proxy (up to ``max_retries`` times).
        """
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            if self.rotator.active_count == 0:
                raise RuntimeError(
                    "All proxies have been exhausted. No proxies available."
                )

            proxy_url = self.rotator.get_next()
            proxy_dict = self.rotator.get_dict(proxy_url)

            try:
                # Merge proxy dict into kwargs (don't overwrite if caller set it)
                kwargs.setdefault("proxies", proxy_dict)
                # Ensure we don't carry over proxies from a previous attempt
                kwargs["proxies"] = proxy_dict

                response = super().request(method, url, **kwargs)
                self.rotator.report_success(proxy_url)
                return response

            except (
                requests.exceptions.ProxyError,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
            ) as exc:
                last_exception = exc
                self.rotator.report_failure(proxy_url)

                if attempt < self.max_retries:
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(delay)

        # All retries exhausted
        raise requests.exceptions.RetryError(
            f"Request to {url} failed after {self.max_retries} retries."
        ) from last_exception

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def add_proxy(self, url: str) -> None:
        """Add a proxy to the underlying rotator."""
        self.rotator.add_proxy(url)

    def remove_proxy(self, url: str) -> None:
        """Remove a proxy from the underlying rotator."""
        self.rotator.remove_proxy(url)

    @property
    def active_proxy_count(self) -> int:
        """Number of proxies currently available."""
        return self.rotator.active_count

    def health_check(self, **kwargs):
        """Run a health check on all proxies."""
        return self.rotator.health_check(**kwargs)

    def __repr__(self) -> str:
        return (
            f"RotatingSession(proxies={self.rotator.active_count}, "
            f"max_retries={self.max_retries})"
        )
