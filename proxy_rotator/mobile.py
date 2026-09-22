"""
Mobile proxies: one endpoint, and a URL that changes its exit IP.

A mobile proxy doesn't hand you a list of IPs to cycle through. You get a
single host:port that sits on a 4G/5G modem, plus a "rotation link". Calling
that link makes the modem drop and redial, and the carrier hands it a new IP.

That changes the usual rotation problem:

* The proxy URL never changes, so there's nothing to round-robin.
* Rotation takes real time. The modem redials, which is typically 10-30 s,
  and requests sent during the redial fail.
* Providers rate-limit rotation per modem and answer ``429`` with a
  ``Retry-After`` header when you call too often.
* The carrier may give you the same IP back. You only know it changed by
  checking.

``MobileProxy`` handles those four things.
"""

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import requests


class RotationError(Exception):
    """The rotation link refused or failed to rotate the IP.

    Attributes:
        status_code: HTTP status returned by the rotation link, if any.
        body: Response body (truncated), useful for provider error messages.
    """

    def __init__(self, message: str, status_code: Optional[int] = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class RotationResult:
    """What happened when ``MobileProxy.rotate()`` ran."""

    old_ip: Optional[str]
    new_ip: Optional[str]
    changed: bool
    waited: float  # seconds spent, including any cooldown sleep


class MobileProxy:
    """A single mobile proxy endpoint with a rotation link.

    Args:
        proxy_url: The proxy, e.g. ``http://user:pass@host:8001`` or
            ``socks5://user:pass@host:9001``.
        rotate_url: The provider's rotation link. A plain ``GET`` to it
            should trigger a new IP.
        min_interval: Seconds to leave between rotations. Set it to your
            provider's limit so you wait locally instead of burning a 429.
        ip_check_url: A URL that returns your IP as plain text.
        request_timeout: Timeout for each HTTP call, in seconds.
        session: Optional ``requests.Session`` to send requests with.
        sleep: Injected for tests. Defaults to ``time.sleep``.
        clock: Injected for tests. Defaults to ``time.monotonic``.

    Example::

        mp = MobileProxy(
            "http://user:pass@sg.example.com:8001",
            "https://provider.example.com/rotate/abc123",
            min_interval=240,
        )
        r = requests.get("https://example.com", proxies=mp.proxies, timeout=30)
        if r.status_code in (403, 429):
            result = mp.rotate()
            print(result.old_ip, "->", result.new_ip)
    """

    def __init__(
        self,
        proxy_url: str,
        rotate_url: str,
        min_interval: float = 0,
        ip_check_url: str = "https://api.ipify.org",
        request_timeout: float = 30,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.proxy_url = proxy_url
        self.rotate_url = rotate_url
        self.min_interval = min_interval
        self.ip_check_url = ip_check_url
        self.request_timeout = request_timeout
        self._session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_rotation: Optional[float] = None

    @property
    def proxies(self) -> Dict[str, str]:
        """A ``requests``-style proxies dict for this endpoint."""
        return {"http": self.proxy_url, "https": self.proxy_url}

    def current_ip(self) -> str:
        """Return the exit IP the target sites currently see."""
        resp = self._session.get(
            self.ip_check_url, proxies=self.proxies, timeout=self.request_timeout
        )
        resp.raise_for_status()
        return resp.text.strip()

    def _safe_ip(self) -> Optional[str]:
        try:
            return self.current_ip()
        except requests.RequestException:
            return None

    def seconds_until_allowed(self) -> float:
        """Seconds left before ``min_interval`` allows another rotation."""
        if self._last_rotation is None or not self.min_interval:
            return 0.0
        left = self.min_interval - (self._clock() - self._last_rotation)
        return max(0.0, left)

    def rotate(
        self,
        wait_for_new_ip: bool = True,
        timeout: float = 90,
        poll_every: float = 3,
        honour_cooldown: bool = True,
    ) -> RotationResult:
        """Ask the provider for a new IP.

        Args:
            wait_for_new_ip: Poll ``ip_check_url`` until the IP differs from
                the one before rotation (or ``timeout`` runs out).
            timeout: Max seconds to wait for the new IP after the rotation
                link has accepted the request.
            poll_every: Seconds between IP checks while waiting.
            honour_cooldown: Sleep out ``min_interval`` (and one ``429
                Retry-After``) instead of raising.

        Returns:
            A ``RotationResult``. ``changed`` is False if the carrier handed
            back the same IP or the new one never showed up before
            ``timeout``. That does happen on mobile networks; call
            ``rotate()`` again after the cooldown if you need a different IP.

        Raises:
            RotationError: the link returned an error, or a 429 arrived with
                ``honour_cooldown=False``.
        """
        started = self._clock()

        wait = self.seconds_until_allowed()
        if wait:
            if not honour_cooldown:
                raise RotationError(f"rotation cooldown: {wait:.0f}s left", 429)
            self._sleep(wait)

        old_ip = self._safe_ip() if wait_for_new_ip else None

        resp = self._call_rotate_url()
        if resp.status_code == 429 and honour_cooldown:
            self._sleep(_retry_after(resp, default=self.min_interval or 60))
            resp = self._call_rotate_url()
        if resp.status_code >= 400:
            raise RotationError(
                f"rotation link returned HTTP {resp.status_code}",
                resp.status_code,
                resp.text[:500],
            )
        self._last_rotation = self._clock()

        new_ip = None
        if wait_for_new_ip:
            deadline = self._clock() + timeout
            while True:
                new_ip = self._safe_ip()
                if new_ip and new_ip != old_ip:
                    break
                if self._clock() >= deadline:
                    break
                self._sleep(poll_every)

        changed = bool(new_ip) and new_ip != old_ip
        return RotationResult(
            old_ip=old_ip,
            new_ip=new_ip,
            changed=changed,
            waited=self._clock() - started,
        )

    def _call_rotate_url(self) -> requests.Response:
        # Deliberately NOT sent through the proxy: the modem is about to drop.
        try:
            return self._session.get(self.rotate_url, timeout=self.request_timeout)
        except requests.RequestException as exc:
            raise RotationError(f"could not reach rotation link: {exc}") from exc

    def __repr__(self) -> str:
        return f"MobileProxy(min_interval={self.min_interval})"


def _retry_after(resp: requests.Response, default: float) -> float:
    value = resp.headers.get("Retry-After", "")
    try:
        return max(0.0, float(value))
    except ValueError:
        return float(default)
