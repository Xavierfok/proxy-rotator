"""
Web scraping example with proxy-rotator.

Uses RotatingSession for automatic proxy rotation and retry logic.
Each request is transparently routed through a different proxy.
"""

import json
from proxy_rotator import RotatingSession

# Replace these with your actual proxy URLs
PROXIES = [
    "http://user:pass@proxy1.example.com:8080",
    "http://user:pass@proxy2.example.com:8080",
    "http://user:pass@proxy3.example.com:3128",
]

# URLs to scrape
URLS = [
    "https://httpbin.org/ip",
    "https://httpbin.org/headers",
    "https://httpbin.org/user-agent",
    "https://httpbin.org/get?page=1",
    "https://httpbin.org/get?page=2",
]


def main():
    # Create a rotating session — every request automatically uses
    # the next proxy in the rotation.
    session = RotatingSession(
        proxies=PROXIES,
        max_retries=3,        # retry up to 3 times on proxy failure
        backoff_factor=0.5,   # wait 0.5s, 1s, 2s between retries
        max_failures=5,       # remove a proxy after 5 consecutive failures
    )

    # Set default headers (works exactly like requests.Session)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    print(f"Starting scrape with {session.active_proxy_count} proxies\n")

    results = []
    for url in URLS:
        try:
            response = session.get(url, timeout=15)
            data = response.json()
            results.append({"url": url, "status": response.status_code, "data": data})
            print(f"[OK]  {url} — status {response.status_code}")
        except Exception as e:
            results.append({"url": url, "error": str(e)})
            print(f"[ERR] {url} — {e}")

    print(f"\nFinished. {session.active_proxy_count} proxies still active.")

    # Save results
    with open("scrape_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Results saved to scrape_results.json")


if __name__ == "__main__":
    main()
