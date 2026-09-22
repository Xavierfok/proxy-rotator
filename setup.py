from setuptools import setup, find_packages
from pathlib import Path

long_description = Path("README.md").read_text(encoding="utf-8")

setup(
    name="proxy-rotator",
    version="1.1.0",
    author="Xavier Fok",
    description=(
        "Rotate proxies in Python scrapers: round-robin pools with health checks "
        "and retries, plus mobile proxies that change IP through a rotation link."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Xavierfok/proxy-rotator",
    project_urls={
        "Bug Tracker": "https://github.com/Xavierfok/proxy-rotator/issues",
        "Documentation": "https://github.com/Xavierfok/proxy-rotator#readme",
        "Proxy Tools & Guides": "https://dataresearchtools.com",
    },
    packages=find_packages(exclude=["examples", "tests"]),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.20.0",
    ],
    extras_require={
        "socks": ["requests[socks]"],
        "dev": [
            "pytest>=7.0",
            "pytest-cov",
            "flake8",
            "black",
            "mypy",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="proxy rotation scraping web-scraping requests socks5 rotating-proxy mobile-proxy 4g-proxy",
)
