"""
Basic usage of proxy-rotator.

Demonstrates round-robin rotation, random selection,
failure tracking, and health checking.
"""

from proxy_rotator import ProxyRotator

# --- 1. Create a rotator with some proxies ---
rotator = ProxyRotator(
    proxies=[
        "http://user:pass@proxy1.example.com:8080",
        "http://user:pass@proxy2.example.com:8080",
        "http://user:pass@proxy3.example.com:3128",
        "socks5://user:pass@proxy4.example.com:1080",
    ],
    max_failures=3,  # remove proxy after 3 consecutive failures
)

print(f"Loaded {rotator.active_count} proxies\n")

# --- 2. Round-robin rotation ---
print("Round-robin rotation:")
for i in range(6):
    proxy = rotator.get_next()
    print(f"  Request {i + 1}: {proxy}")

# --- 3. Random selection ---
print("\nRandom selection:")
for i in range(3):
    proxy = rotator.get_random()
    print(f"  Random pick {i + 1}: {proxy}")

# --- 4. Add / remove proxies at runtime ---
rotator.add_proxy("http://proxy5.example.com:8888")
print(f"\nAfter adding proxy5: {rotator.active_count} proxies")

rotator.remove_proxy("http://user:pass@proxy1.example.com:8080")
print(f"After removing proxy1: {rotator.active_count} proxies")

# --- 5. Failure tracking ---
bad_proxy = "http://user:pass@proxy2.example.com:8080"
print(f"\nSimulating failures for {bad_proxy}:")
for i in range(3):
    rotator.report_failure(bad_proxy)
    print(f"  Failure {i + 1} reported — still active: {bad_proxy in rotator.proxies}")

print(f"Proxies remaining: {rotator.active_count}")

# --- 6. Get a requests-compatible proxy dict ---
proxy = rotator.get_next()
proxy_dict = rotator.get_dict(proxy)
print(f"\nProxy dict for requests: {proxy_dict}")

# --- 7. Load from file ---
# rotator = ProxyRotator.from_file("proxies.txt")

# --- 8. Health check (uncomment to run against real proxies) ---
# results = rotator.health_check()
# for url, healthy in results.items():
#     print(f"  {url}: {'OK' if healthy else 'DEAD'}")
