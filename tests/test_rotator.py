import pytest

from proxy_rotator import ProxyRotator

P = ["http://a.example.com:8080", "http://b.example.com:8080", "socks5://c.example.com:1080"]


def test_round_robin_wraps():
    r = ProxyRotator(P)
    assert [r.get_next() for _ in range(4)] == P + [P[0]]


def test_rejects_unknown_scheme():
    with pytest.raises(ValueError):
        ProxyRotator(["ftp://x.example.com:21"])


def test_failures_remove_proxy_after_threshold():
    r = ProxyRotator(P, max_failures=2)
    r.report_failure(P[0])
    assert r.active_count == 3
    r.report_failure(P[0])
    assert P[0] not in r.proxies


def test_success_resets_failure_count():
    r = ProxyRotator(P, max_failures=2)
    r.report_failure(P[1])
    r.report_success(P[1])
    r.report_failure(P[1])
    assert P[1] in r.proxies


def test_from_file_skips_comments(tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("# pool\n\nhttp://a.example.com:8080\n  http://b.example.com:8080  \n")
    r = ProxyRotator.from_file(str(f))
    assert r.proxies == ["http://a.example.com:8080", "http://b.example.com:8080"]


def test_empty_pool_raises():
    with pytest.raises(RuntimeError):
        ProxyRotator().get_next()
