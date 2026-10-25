"""Web download-job and Core facade contracts."""

from importlib import import_module


def test_single_download_job_calls_core_facade(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    app_module = import_module("xduclassvideodownloader.web.app")
    downloads = import_module("xduclassvideodownloader.web.downloads")
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(tmp_path / "auth.ini"))
    captured = []
    monkeypatch.setattr(downloads, "download_course", lambda options: captured.append(options) or True)

    response = app_module.create_app({"TESTING": True}).test_client().post(
        "/api/download/start",
        json={"mode": "single", "live_id": "123", "single": 0, "merge": True, "video_type": "both"},
    )
    job = app_module.jobs.get(response.get_json()["job_id"])
    job.thread.join(timeout=2)

    assert response.status_code == 200
    assert captured[0].live_id == "123"


def test_batch_selection_uses_facade_without_mutating_saved_config(monkeypatch, tmp_path):
    downloads = import_module("xduclassvideodownloader.web.downloads")
    config_module = import_module("xduclassvideodownloader.core.config")
    config_file = tmp_path / "automation_config.ini"
    config = config_module.CaseSensitiveConfigParser()
    config["DEFAULT"] = {"user_id": "123456", "term_year": "2026", "term_id": "1", "video_type": "both"}
    config["101"] = {"course_code": "CS101", "course_name": "数据结构", "live_id": "10", "download": "no"}
    config_module.safe_write_config(config, str(config_file))
    monkeypatch.setattr(downloads, "AUTOMATION_CONFIG_FILE", str(config_file))
    captured = {}
    monkeypatch.setattr(
        downloads,
        "download_courses",
        lambda config, selected_sections, video_type: captured.update(
            config=config, selected_sections=selected_sections, video_type=video_type
        )
        or True,
    )

    assert downloads.run_batch_download(["101"], "ppt") is True
    assert captured["selected_sections"] == {"101"}
    assert config_module.safe_read_config(str(config_file))["101"]["download"] == "no"
