import pytest
import requests

from proxy_rotator import MobileProxy, RotationError


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Scripted stand-in for requests.Session.

    ``ips`` is consumed by calls to the IP-check URL, ``rotations`` by calls
    to the rotation URL. An Exception instance in either list is raised.
    """

    def __init__(self, ips, rotations):
        self.ips = list(ips)
        self.rotations = list(rotations)
        self.calls = []

    def get(self, url, proxies=None, timeout=None):
        self.calls.append((url, proxies))
        queue = self.rotations if "rotate" in url else self.ips
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, FakeResponse):
            return item
        return FakeResponse(200, item)


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def sleep(self, s):
        self.slept.append(s)
        self.now += s

    def __call__(self):
        return self.now


PROXY = "http://u:p@sg.example.com:8001"
ROTATE = "https://provider.example.com/rotate/tok"


def make(ips, rotations, **kw):
    clock = FakeClock()
    session = FakeSession(ips, rotations)
    mp = MobileProxy(PROXY, ROTATE, session=session, sleep=clock.sleep, clock=clock, **kw)
    return mp, session, clock


def test_proxies_dict():
    mp, _, _ = make([], [])
    assert mp.proxies == {"http": PROXY, "https": PROXY}


def test_rotate_waits_until_ip_changes():
    # old IP, then the modem is mid-redial (error), then same IP, then new IP
    mp, session, clock = make(
        ["1.1.1.1", requests.ConnectionError("redialling"), "1.1.1.1", "2.2.2.2"],
        [FakeResponse(200, '{"success": true}')],
        min_interval=240,
    )
    result = mp.rotate(poll_every=3)
    assert result.old_ip == "1.1.1.1"
    assert result.new_ip == "2.2.2.2"
    assert result.changed is True
    assert clock.slept == [3, 3]


def test_rotation_link_is_not_sent_through_the_proxy():
    mp, session, _ = make(["1.1.1.1", "2.2.2.2"], [FakeResponse(200)])
    mp.rotate()
    rotate_calls = [c for c in session.calls if c[0] == ROTATE]
    assert rotate_calls == [(ROTATE, None)]


def test_same_ip_back_reports_unchanged():
    mp, _, _ = make(["1.1.1.1"] + ["1.1.1.1"] * 50, [FakeResponse(200)])
    result = mp.rotate(timeout=9, poll_every=3)
    assert result.changed is False
    assert result.new_ip == "1.1.1.1"


def test_min_interval_sleeps_before_second_rotation():
    mp, _, clock = make(
        ["1.1.1.1", "2.2.2.2", "2.2.2.2", "3.3.3.3"],
        [FakeResponse(200), FakeResponse(200)],
        min_interval=240,
    )
    mp.rotate()
    clock.now += 40  # 40 s of scraping
    mp.rotate()
    assert 200 in clock.slept


def test_min_interval_raises_when_not_honoured():
    mp, _, _ = make(["1.1.1.1", "2.2.2.2"], [FakeResponse(200)], min_interval=240)
    mp.rotate()
    with pytest.raises(RotationError) as exc:
        mp.rotate(honour_cooldown=False)
    assert exc.value.status_code == 429


def test_429_retry_after_is_honoured_once():
    mp, _, clock = make(
        ["1.1.1.1", "2.2.2.2"],
        [FakeResponse(429, "too often", {"Retry-After": "37"}), FakeResponse(200)],
    )
    result = mp.rotate()
    assert 37.0 in clock.slept
    assert result.changed


def test_error_status_raises_with_body():
    mp, _, _ = make(["1.1.1.1"], [FakeResponse(410, "this rotation link no longer exists")])
    with pytest.raises(RotationError) as exc:
        mp.rotate()
    assert exc.value.status_code == 410
    assert "no longer exists" in exc.value.body


def test_unreachable_rotation_link_raises():
    mp, _, _ = make(["1.1.1.1"], [requests.ConnectionError("down")])
    with pytest.raises(RotationError):
        mp.rotate()


def test_rotate_without_waiting_skips_ip_checks():
    mp, session, _ = make([], [FakeResponse(200)])
    result = mp.rotate(wait_for_new_ip=False)
    assert result.old_ip is None and result.new_ip is None
    assert [c[0] for c in session.calls] == [ROTATE]
