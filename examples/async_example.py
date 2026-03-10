"""
Async web scraping example using proxy-rotator with aiohttp.

Demonstrates how to use ProxyRotator in an async context for
high-concurrency scraping with rotating proxies.

Requirements:
    pip install aiohttp proxy-rotator
"""

import asyncio
import aiohttp
from proxy_rotator import ProxyRotator

# Replace these with your actual proxy URLs
PROXIES = [
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
    "http://user:pass@proxy3.example.com:3128",
]

# Create the rotator (thread-safe, works fine with asyncio)
rotator = ProxyRotator(proxies=PROXIES, max_failures=3)


async def fetch(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch a URL through a rotating proxy."""
    proxy = rotator.get_next()
    try:
        async with session.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
            rotator.report_success(proxy)
            return {"url": url, "proxy": proxy, "status": resp.status, "data": data}
    except Exception as e:
        rotator.report_failure(proxy)
        return {"url": url, "proxy": proxy, "error": str(e)}


async def fetch_with_retry(session: aiohttp.ClientSession, url: str, max_retries: int = 3) -> dict:
    """Fetch a URL with automatic retry using different proxies."""
    for attempt in range(1, max_retries + 1):
        if rotator.active_count == 0:
            return {"url": url, "error": "No proxies available"}

        result = await fetch(session, url)
        if "error" not in result:
            return result

        if attempt < max_retries:
            await asyncio.sleep(0.5 * attempt)  # simple backoff

    return result  # return last failed result


async def main():
    urls = [
        "https://httpbin.org/ip",
        "https://httpbin.org/headers",
        "https://httpbin.org/get?page=1",
        "https://httpbin.org/get?page=2",
        "https://httpbin.org/get?page=3",
        "https://httpbin.org/user-agent",
        "https://httpbin.org/get?page=4",
        "https://httpbin.org/get?page=5",
    ]

    print(f"Fetching {len(urls)} URLs with {rotator.active_count} proxies\n")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        # Run all requests concurrently
        tasks = [fetch_with_retry(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    # Print results
    for result in results:
        if "error" in result:
            print(f"[ERR] {result['url']} via {result.get('proxy', 'N/A')} — {result['error']}")
        else:
            print(f"[OK]  {result['url']} via {result['proxy']} — status {result['status']}")

    print(f"\nProxies still active: {rotator.active_count}")


if __name__ == "__main__":
    asyncio.run(main())
