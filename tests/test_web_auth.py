"""WebUI authentication settings and QR lifecycle contracts."""

from importlib import import_module


def test_auth_status_never_returns_password(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    web_auth = import_module("xduclassvideodownloader.web.auth")
    app_module = import_module("xduclassvideodownloader.web.app")
    config_module = import_module("xduclassvideodownloader.core.config")
    auth_file = tmp_path / "auth.ini"
    config = config_module.CaseSensitiveConfigParser()
    config["SETTINGS"] = {"auth_method": "ids", "save_auth_info": "True"}
    config["IDS_CREDENTIALS"] = {"username": "user-1", "password": "super-secret"}
    config_module.safe_write_config(config, str(auth_file))
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(auth_file))
    monkeypatch.setattr(web_auth, "AUTH_CONFIG_FILE", str(auth_file))
    monkeypatch.setattr(
        web_auth,
        "login_to_chaoxing_via_ids",
        lambda *args: (_ for _ in ()).throw(RuntimeError("network disabled in test")),
    )

    response = app_module.create_app({"TESTING": True}).test_client().get("/api/settings/auth")

    assert response.status_code == 200
    assert b"super-secret" not in response.data
    assert b"user-1" not in response.data


def test_saving_auth_clears_stale_runtime_cache(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    web_auth = import_module("xduclassvideodownloader.web.auth")
    app_module = import_module("xduclassvideodownloader.web.app")
    config_module = import_module("xduclassvideodownloader.core.config")
    auth_file = tmp_path / "auth.ini"
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(auth_file))
    monkeypatch.setattr(web_auth, "AUTH_CONFIG_FILE", str(auth_file))
    cleared = []
    monkeypatch.setattr(web_auth, "clear_runtime_auth_cache", lambda: cleared.append(True))

    response = app_module.create_app({"TESTING": True}).test_client().post(
        "/api/settings/auth",
        json={"auth_method": "ids", "save_auth_info": False},
    )

    assert response.status_code == 200
    assert cleared == [True]
    assert config_module.safe_read_config(str(auth_file))["SETTINGS"]["save_auth_info"] == "False"


def test_qr_job_uses_core_session_and_handles_success(monkeypatch, tmp_path):
    app_module = import_module("xduclassvideodownloader.web.app")
    auth_module = import_module("xduclassvideodownloader.core.auth")

    class FakeSession:
        def __init__(self, **kwargs):
            self.path = kwargs["qr_image_path"]

        def create_qr_image(self):
            from pathlib import Path

            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as image:
                image.write(b"png")

        def poll(self, is_cancelled=None):
            return auth_module.QRLoginResult(
                "success", "ok", {"_d": "a", "UID": "b", "vc3": "c", "fid": "16820"}
            )

    monkeypatch.setattr(app_module, "ChaoxingQRLoginSession", FakeSession)
    saved = []
    monkeypatch.setattr(app_module, "_save_qr_cookies", lambda cookies: saved.append(cookies))
    monkeypatch.setattr(app_module, "get_app_path", lambda *parts: tmp_path.joinpath(*parts))

    job = app_module.QRLoginJob()
    job._run()

    assert job.status == "success"
    assert saved[0]["UID"] == "b"


def test_qr_job_cancel_and_timeout_are_terminal(monkeypatch, tmp_path):
    app_module = import_module("xduclassvideodownloader.web.app")
    auth_module = import_module("xduclassvideodownloader.core.auth")

    class FakeSession:
        result = auth_module.QRLoginResult("failed", "timeout")

        def __init__(self, **kwargs):
            self.path = kwargs["qr_image_path"]

        def create_qr_image(self):
            from pathlib import Path

            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as image:
                image.write(b"png")

        def poll(self, is_cancelled=None):
            return self.result

    monkeypatch.setattr(app_module, "ChaoxingQRLoginSession", FakeSession)
    monkeypatch.setattr(app_module, "get_app_path", lambda *parts: tmp_path.joinpath(*parts))
    cancelled = app_module.QRLoginJob()
    cancelled.cancel()
    cancelled._run()
    assert cancelled.status == "cancelled"

    timed_out = app_module.QRLoginJob()
    timed_out._run()
    assert timed_out.status == "failed"
    assert timed_out.message == "timeout"
