"""
Scrape through one mobile proxy and rotate the IP only when a site pushes back.

Set two environment variables first:

    PROXY_URL   http://user:pass@host:port   (from your provider's dashboard)
    ROTATE_URL  the rotation link for that same port

Then:  python examples/mobile_proxy_example.py
"""

import os
import sys

import requests

from proxy_rotator import MobileProxy, RotationError

proxy_url = os.environ.get("PROXY_URL")
rotate_url = os.environ.get("ROTATE_URL")
if not proxy_url or not rotate_url:
    sys.exit("set PROXY_URL and ROTATE_URL first")

# 240 s = 4 minutes, Singapore Mobile Proxy's per-modem limit.
# Use whatever your provider enforces.
mp = MobileProxy(proxy_url, rotate_url, min_interval=240)
print("starting IP:", mp.current_ip())

urls = [
    "https://httpbin.org/status/200",
    "https://httpbin.org/status/429",  # pretend we got rate-limited
    "https://httpbin.org/status/200",
]

for url in urls:
    resp = requests.get(url, proxies=mp.proxies, timeout=30)
    print(resp.status_code, url)

    if resp.status_code in (403, 429):
        try:
            result = mp.rotate()
        except RotationError as exc:
            print("rotation failed:", exc, exc.body)
            break
        if result.changed:
            print(f"rotated {result.old_ip} -> {result.new_ip} in {result.waited:.0f}s")
        else:
            # Carriers sometimes hand back the same address. Wait out the
            # cooldown and try again if you need a different one.
            print("carrier gave back the same IP:", result.new_ip)
