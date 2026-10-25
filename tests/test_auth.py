"""Authentication cache and secret-redaction contracts."""


def test_clear_runtime_auth_cache_forces_next_auth_resolution(monkeypatch, tmp_path):
    from xduclassvideodownloader.core import auth
    from xduclassvideodownloader.core.paths import set_runtime_dir

    set_runtime_dir(tmp_path)
    auth.set_runtime_auth_cookies({"_d": "a", "UID": "b", "vc3": "c"})
    assert auth.get_auth_cookies() == {"_d": "a", "UID": "b", "vc3": "c"}
    auth.clear_runtime_auth_cache()
    monkeypatch.setattr(auth, "_read_saved_auth_cookies", lambda: {"_d": "d", "UID": "e", "vc3": "f"})

    assert auth.get_auth_cookies() == {"_d": "d", "UID": "e", "vc3": "f"}


def test_auth_cookie_validation_and_redaction_do_not_expose_full_values():
    from xduclassvideodownloader.core.auth import has_valid_auth_cookies, redact_auth_value

    cookies = {"_d": "cookie-secret", "UID": "uid-secret", "vc3": "vc3-secret"}
    assert has_valid_auth_cookies(cookies)
    redacted = redact_auth_value("password-secret")
    assert "password-secret" not in redacted
    assert "cookie-secret" not in redact_auth_value(cookies["_d"])


def test_missing_auth_preserves_interactive_first_run_flow(monkeypatch):
    from xduclassvideodownloader.core import auth
    from xduclassvideodownloader.core.config import CaseSensitiveConfigParser

    answers = iter(["1", "1", "123456", "password"])
    saved = {}
    auth.clear_runtime_auth_cache()
    monkeypatch.setattr(auth, "_read_auth_settings", lambda: CaseSensitiveConfigParser())
    monkeypatch.setattr(auth, "_read_saved_auth_cookies", lambda: {})
    monkeypatch.setattr(auth, "user_input_with_check", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        auth,
        "login_to_chaoxing_via_ids",
        lambda username, password: {"_d": "a", "UID": "b", "vc3": "c"},
    )
    monkeypatch.setattr(
        auth,
        "_save_auth_cookies",
        lambda cookies, **kwargs: saved.update(cookies=cookies, settings=kwargs),
    )

    cookies = auth.get_auth_cookies()

    assert cookies["UID"] == "b"
    assert saved["settings"]["auth_method"] == "ids"
    assert saved["settings"]["username"] == "123456"
