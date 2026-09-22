# proxy-rotator

[![tests](https://github.com/Xavierfok/proxy-rotator/actions/workflows/tests.yml/badge.svg)](https://github.com/Xavierfok/proxy-rotator/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Small Python library for rotating proxies in scrapers. It covers two different jobs:

1. You have a **list of proxies** and want to spread requests across them, drop the dead ones and retry on failure. That's `ProxyRotator` and `RotatingSession`.
2. You have a **mobile proxy**: one host:port on a 4G modem, plus a URL that makes the modem redial for a new IP. That's `MobileProxy`.

The only dependency is `requests`.

## Install

It isn't on PyPI yet, so install from GitHub:

```bash
pip install git+https://github.com/Xavierfok/proxy-rotator.git

# with SOCKS5 support
pip install "proxy-rotator[socks] @ git+https://github.com/Xavierfok/proxy-rotator.git"
```

## Mobile proxies

With a mobile proxy the address you connect to never changes. The IP behind it changes when you hit the provider's rotation link. That trips people up in a few ways:

- The modem has to redial, which takes 10 to 30 seconds, and requests sent during the redial fail.
- Providers cap how often you can rotate. Mine allows once every 4 minutes per modem and answers `429` with a `Retry-After` header if you go faster.
- The carrier can hand back the same IP. You only find out by checking.
- If you send the rotation call *through* the proxy, it can die along with the connection it's resetting.

`MobileProxy` waits out the cooldown, calls the link directly, then polls an IP echo service until the address actually changes.

```python
import requests
from proxy_rotator import MobileProxy

mp = MobileProxy(
    "http://user:pass@sg.example.com:8001",       # the proxy
    "https://provider.example.com/rotate/abc123",  # its rotation link
    min_interval=240,                              # your provider's limit, in seconds
)

r = requests.get("https://example.com/search?q=shoes", proxies=mp.proxies, timeout=30)
if r.status_code in (403, 429):
    result = mp.rotate()
    print(result.old_ip, "->", result.new_ip, "changed:", result.changed, f"{result.waited:.0f}s")
```

`rotate()` returns a `RotationResult` with `old_ip`, `new_ip`, `changed` and `waited`. It raises `RotationError` (with `.status_code` and `.body`) when the link refuses, for example a `410` once a port has been cancelled. Pass `honour_cooldown=False` if you'd rather get the error than have it sleep.

I'd rotate when a site pushes back (a 403, a 429, a captcha page), not on a timer. A mobile IP is shared with real phone users behind the carrier's NAT, so sites are slow to block one, and every rotation costs you about 20 seconds of downtime.

A full script is in [`examples/mobile_proxy_example.py`](examples/mobile_proxy_example.py).

What I haven't tested: the unit tests in `tests/` fake the network. I wrote `MobileProxy` against the rotation links of [Singapore Mobile Proxy](https://singaporemobileproxy.com/?utm_source=github&utm_medium=repo&utm_campaign=proxy_rotator), which I run. Any provider whose link rotates on a plain `GET` should work, but I haven't tried the others. If yours behaves differently, open an issue.

## Proxy lists

```python
from proxy_rotator import ProxyRotator

rotator = ProxyRotator([
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
    "socks5://user:pass@proxy3.example.com:1080",
])

rotator.get_next()    # round-robin
rotator.get_random()  # random pick

rotator.add_proxy("http://proxy4.example.com:8080")
rotator.remove_proxy("http://proxy1.example.com:8080")
print(rotator.active_count)
```

Load them from a file (one URL per line; blank lines and `#` comments are skipped):

```python
rotator = ProxyRotator.from_file("proxies.txt")
```

### RotatingSession

`RotatingSession` subclasses `requests.Session`. Each request goes out through the next proxy, and a failed one is retried on a different proxy with exponential backoff.

```python
from proxy_rotator import RotatingSession

session = RotatingSession(
    proxies=["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"],
    max_retries=3,
    backoff_factor=0.5,
)
print(session.get("https://httpbin.org/ip").json())
```

It's thread-safe, so one session can be shared across a `ThreadPoolExecutor`.

### Health checks

```python
rotator = ProxyRotator(
    proxies=["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"],
    max_failures=3,
    health_check_url="https://httpbin.org/ip",
    health_check_timeout=10,
)

for proxy, ok in rotator.health_check().items():
    print(proxy, "OK" if ok else "DEAD")
```

A proxy that fails `max_failures` times in a row leaves the pool.

### httpx and aiohttp

The rotator just hands out URLs, so it works with any client:

```python
import httpx
with httpx.Client(proxy=rotator.get_next()) as client:
    client.get("https://httpbin.org/ip")
```

```python
async with aiohttp.ClientSession() as s:
    async with s.get("https://httpbin.org/ip", proxy=rotator.get_next()) as r:
        print(await r.text())
```

See [`examples/`](examples/) for longer versions.

## API reference

### `MobileProxy(proxy_url, rotate_url, ...)`

| Argument / method | Default | What it does |
|---|---|---|
| `min_interval` | `0` | Seconds to leave between rotations |
| `ip_check_url` | `https://api.ipify.org` | Plain-text IP echo used to confirm a change |
| `request_timeout` | `30` | Per-request timeout, seconds |
| `proxies` | | `requests`-style dict for the endpoint |
| `current_ip()` | | Exit IP right now |
| `rotate(wait_for_new_ip=True, timeout=90, poll_every=3, honour_cooldown=True)` | | Rotate and return a `RotationResult` |
| `seconds_until_allowed()` | | Time left on the local cooldown |

### `ProxyRotator(proxies, max_failures=5, health_check_url=..., health_check_timeout=10)`

| Method | What it does |
|---|---|
| `get_next()` | Next proxy, round-robin |
| `get_random()` | Random proxy |
| `get_dict(proxy=None)` | `requests`-style dict |
| `add_proxy(url)` / `remove_proxy(url)` | Change the pool |
| `report_failure(url)` / `report_success(url)` | Update the failure counter |
| `health_check(max_workers=10)` | Test every proxy in parallel |
| `from_file(path)` | Build from a text file |
| `active_count` | Proxies left in the pool |

### `RotatingSession(proxies, max_retries=3, backoff_factor=0.3, max_failures=5, rotator=None)`

A `requests.Session`. Also has `add_proxy`, `remove_proxy`, `health_check` and `active_proxy_count`.

Supported URL schemes: `http`, `https`, `socks5`, `socks5h`.

## Tests

```bash
pip install -e . pytest
pytest
```

## Where to get proxies

I run [Singapore Mobile Proxy](https://singaporemobileproxy.com/?utm_source=github&utm_medium=repo&utm_campaign=proxy_rotator): dedicated 4G lines on Singtel and M1, one customer per line, from $40 a month, with a 24-hour free trial. It only does Singapore. For comparisons of other providers, [DataResearchTools](https://dataresearchtools.com/?utm_source=github&utm_medium=repo&utm_campaign=proxy_rotator) (also mine) has reviews and scraping guides.

## License

MIT. See [LICENSE](LICENSE).
