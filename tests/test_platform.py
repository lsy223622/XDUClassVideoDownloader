"""Mocked Core platform contracts."""


def test_update_check_failure_allows_start(monkeypatch):
    from xduclassvideodownloader.core import platform as platform_module

    class FailingSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("offline")

    monkeypatch.setattr(platform_module, "create_session", lambda: FailingSession())
    assert platform_module.check_update() is True


def test_platform_auth_headers_require_explicit_cookies():
    from xduclassvideodownloader.core.platform import get_authenticated_headers

    try:
        get_authenticated_headers()
    except ValueError as exc:
        assert "认证" in str(exc)
    else:
        raise AssertionError("platform must not resolve auth state implicitly")


def test_platform_auth_headers_format_explicit_cookies():
    from xduclassvideodownloader.core.platform import get_authenticated_headers

    headers = get_authenticated_headers({"_d": "a", "UID": "b", "vc3": "c"})
    assert "_d=a" in headers["Cookie"]
    assert "UID=b" in headers["Cookie"]
