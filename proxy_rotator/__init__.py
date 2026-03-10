"""
proxy-rotator: Lightweight proxy rotation for web scraping.

Supports HTTP/HTTPS/SOCKS5 proxies with automatic rotation,
health checking, and retry logic.
"""

from .rotator import ProxyRotator
from .session import RotatingSession

__version__ = "1.0.0"
__all__ = ["ProxyRotator", "RotatingSession"]
