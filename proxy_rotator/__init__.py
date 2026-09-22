"""
proxy-rotator: Lightweight proxy rotation for web scraping.

Supports HTTP/HTTPS/SOCKS5 proxies with automatic rotation,
health checking, and retry logic. ``MobileProxy`` covers the other
kind of rotation: one mobile endpoint whose IP changes when you call
the provider's rotation link.
"""

from .mobile import MobileProxy, RotationError, RotationResult
from .rotator import ProxyRotator
from .session import RotatingSession

__version__ = "1.1.0"
__all__ = [
    "MobileProxy",
    "ProxyRotator",
    "RotatingSession",
    "RotationError",
    "RotationResult",
]
