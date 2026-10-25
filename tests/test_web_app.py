"""WebUI app-factory and access-policy contracts."""

from importlib import import_module


def test_create_app_serves_index(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    app_module = import_module("xduclassvideodownloader.web.app")
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(tmp_path / "auth.ini"))

    response = app_module.create_app({"TESTING": True}).test_client().get("/")

    assert response.status_code == 200
    assert b"XDUClassVideoDownloader" in response.data


def test_disallowed_client_is_403(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    app_module = import_module("xduclassvideodownloader.web.app")
    config_module = import_module("xduclassvideodownloader.core.config")
    auth_file = tmp_path / "auth.ini"
    config = config_module.CaseSensitiveConfigParser()
    config["WEBUI"] = {"allowed_clients": "192.0.2.0/24"}
    config_module.safe_write_config(config, str(auth_file))
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(auth_file))

    response = app_module.create_app({"TESTING": True}).test_client().get(
        "/api/app/info", environ_base={"REMOTE_ADDR": "127.0.0.1"}
    )

    assert response.status_code == 403
