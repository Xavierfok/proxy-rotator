# proxy-rotator

[![PyPI version](https://badge.fury.io/py/proxy-rotator.svg)](https://pypi.org/project/proxy-rotator/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)

**Lightweight Python library for rotating proxies in web scraping projects.** Supports HTTP/HTTPS/SOCKS5 proxies with automatic rotation, health checking, and retry logic.

## Features

- **Round-robin & random rotation** -- cycle through proxies sequentially or pick one at random
- **Automatic health checking** -- periodically test proxies and remove dead ones
- **Configurable failure threshold** -- proxies are sidelined after N consecutive failures
- **Thread-safe** -- safe to use across multiple threads with built-in locking
- **Protocol support** -- works with HTTP, HTTPS, and SOCKS5 proxies
- **Drop-in session wrapper** -- `RotatingSession` extends `requests.Session` so every request automatically uses a different proxy
- **Async-friendly** -- easy to integrate with `aiohttp` and `httpx`
- **Zero heavy dependencies** -- core library only requires `requests`

## Installation

```bash
pip install proxy-rotator
```

For SOCKS5 support:

```bash
pip install proxy-rotator[socks]
```

## Quick Start

```python
from proxy_rotator import ProxyRotator

proxies = [
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
    "socks5://user:pass@proxy3.example.com:1080",
]

rotator = ProxyRotator(proxies)

# Round-robin rotation
proxy = rotator.get_next()
print(proxy)  # → http://user:pass@proxy1.example.com:8080

proxy = rotator.get_next()
print(proxy)  # → http://user:pass@proxy2.example.com:8080

# Random selection
proxy = rotator.get_random()
```

## Usage

### Basic Proxy Rotation

```python
from proxy_rotator import ProxyRotator

rotator = ProxyRotator([
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
    "http://proxy3.example.com:8080",
])

# Add or remove proxies at runtime
rotator.add_proxy("http://proxy4.example.com:8080")
rotator.remove_proxy("http://proxy1.example.com:8080")

# Check how many proxies are alive
print(f"Active proxies: {rotator.active_count}")
```

### Drop-in Rotating Session (requests)

`RotatingSession` is a subclass of `requests.Session`. Every call to `.get()`, `.post()`, etc. automatically rotates to the next proxy.

```python
from proxy_rotator import RotatingSession

session = RotatingSession(
    proxies=[
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080",
    ],
    max_retries=3,        # retry on failure with the next proxy
    backoff_factor=0.5,   # exponential backoff between retries
)

# Every request uses a different proxy -- no extra code needed
response = session.get("https://httpbin.org/ip")
print(response.json())

response = session.get("https://httpbin.org/ip")
print(response.json())
```

### Using with httpx

```python
import httpx
from proxy_rotator import ProxyRotator

rotator = ProxyRotator([
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
])

for url in urls_to_scrape:
    proxy = rotator.get_next()
    with httpx.Client(proxy=proxy) as client:
        response = client.get(url)
        print(response.text)
```

### Async Usage with aiohttp

```python
import aiohttp
import asyncio
from proxy_rotator import ProxyRotator

rotator = ProxyRotator([
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
])

async def fetch(url):
    proxy = rotator.get_next()
    async with aiohttp.ClientSession() as session:
        async with session.get(url, proxy=proxy) as response:
            return await response.text()

async def main():
    urls = ["https://httpbin.org/ip"] * 5
    tasks = [fetch(url) for url in urls]
    results = await asyncio.gather(*tasks)
    for r in results:
        print(r)

asyncio.run(main())
```

### Health Checking

Run a health check to test all proxies and remove unresponsive ones:

```python
from proxy_rotator import ProxyRotator

rotator = ProxyRotator(
    proxies=["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"],
    max_failures=3,          # remove proxy after 3 consecutive failures
    health_check_url="https://httpbin.org/ip",
    health_check_timeout=10, # seconds
)

# Test all proxies (runs in parallel using threads)
results = rotator.health_check()
for proxy_url, is_healthy in results.items():
    status = "OK" if is_healthy else "DEAD"
    print(f"  {proxy_url}: {status}")

print(f"Healthy proxies remaining: {rotator.active_count}")
```

### Loading Proxies from a File

```python
from proxy_rotator import ProxyRotator

rotator = ProxyRotator.from_file("proxies.txt")
# proxies.txt should contain one proxy URL per line
```

### Thread-Safe Concurrent Usage

```python
from concurrent.futures import ThreadPoolExecutor
from proxy_rotator import RotatingSession

session = RotatingSession(
    proxies=["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"],
    max_retries=2,
)

def fetch(url):
    return session.get(url).text

with ThreadPoolExecutor(max_workers=10) as pool:
    urls = ["https://httpbin.org/ip"] * 20
    results = list(pool.map(fetch, urls))
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `proxies` | `[]` | List of proxy URLs |
| `max_failures` | `5` | Consecutive failures before a proxy is removed |
| `health_check_url` | `https://httpbin.org/ip` | URL used for health checks |
| `health_check_timeout` | `10` | Timeout in seconds for health check requests |

## Proxy URL Formats

```
http://host:port
http://username:password@host:port
https://host:port
socks5://host:port
socks5://username:password@host:port
```

## API Reference

### `ProxyRotator`

| Method | Description |
|--------|-------------|
| `get_next()` | Return the next proxy (round-robin) |
| `get_random()` | Return a random proxy |
| `add_proxy(url)` | Add a proxy to the pool |
| `remove_proxy(url)` | Remove a proxy from the pool |
| `report_failure(url)` | Record a failure; removes proxy after `max_failures` |
| `report_success(url)` | Reset a proxy's failure counter |
| `health_check()` | Test all proxies and return results dict |
| `active_count` | Number of currently active proxies |
| `from_file(path)` | Class method to load proxies from a text file |

### `RotatingSession`

Extends `requests.Session` with automatic proxy rotation.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `proxies` | required | List of proxy URLs |
| `max_retries` | `3` | Max retries per request |
| `backoff_factor` | `0.3` | Exponential backoff multiplier |
| `max_failures` | `5` | Failures before proxy removal |

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License -- see the [LICENSE](LICENSE) file for details.

## Recommended Proxy Providers

If you need reliable proxies for your scraping projects, here are some recommendations:

- For proxy comparison tools, reviews, and scraping guides, visit [DataResearchTools.com](https://dataresearchtools.com)
