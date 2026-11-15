"""Structured progress and native download queue contracts."""

from importlib import import_module

from xduclassvideodownloader.core.models import CourseDownloadOptions


def test_native_batch_enqueues_live_ids_without_saved_config(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    app = import_module("xduclassvideodownloader.web.app")
    downloads = import_module("xduclassvideodownloader.web.downloads")
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(tmp_path / "auth.ini"))
    monkeypatch.setattr(app, "AUTOMATION_CONFIG_FILE", str(tmp_path / "missing.ini"))
    monkeypatch.setattr(app, "jobs", downloads.DownloadJobManager())
    captured = []

    def download(options, *, auth_cookies, observer, checkpoint):
        captured.append(options)
        observer("course", name="数据结构", code="CS101")
        observer("error", message="课程读取失败")
        return False

    def authenticate(*, interactive, fid=None):
        assert interactive is False
        assert fid == "16820"
        return {"UID": "123"}

    monkeypatch.setattr(downloads, "get_auth_cookies", authenticate)
    monkeypatch.setattr(downloads, "download_course", download)
    client = app.create_app({"TESTING": True}).test_client()
    response = client.post("/api/download/start", json={
        "mode": "batch", "video_type": "ppt",
        "courses": [{"live_id": "123"}, {"live_id": "456"}],
    })
    assert response.status_code == 200
    for job_id in response.json["job_ids"]:
        app.jobs.get(job_id).thread.join(timeout=3)
    assert captured == [
        CourseDownloadOptions("123", video_type="ppt"),
        CourseDownloadOptions("456", video_type="ppt"),
    ]
    tasks = client.get("/api/download/jobs").json["jobs"]
    assert [task["status"] for task in tasks] == ["failed", "failed"]
    assert tasks[0]["name"] == "数据结构"
    assert tasks[0]["errors"][0]["message"] == "课程读取失败"


def test_scan_keeps_saved_config_until_explicit_save(monkeypatch, tmp_path):
    access = import_module("xduclassvideodownloader.web.access")
    app = import_module("xduclassvideodownloader.web.app")
    settings = import_module("xduclassvideodownloader.web.settings")
    config = import_module("xduclassvideodownloader.core.config")
    config_path = tmp_path / "automation.ini"
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(tmp_path / "auth.ini"))
    monkeypatch.setattr(app, "AUTOMATION_CONFIG_FILE", str(config_path))
    monkeypatch.setattr(settings, "get_auth_cookies", lambda *, interactive: {"UID": "123456"})
    monkeypatch.setattr(settings, "scan_term_courses", lambda *args, **kwargs: {
        101: {"courseCode": "CS101", "courseName": "数据结构", "id": 1234},
    })
    client = app.create_app({"TESTING": True}).test_client()
    params = {"uid": "123456", "year": 2026, "term": 1, "video_type": "teacher"}
    response = client.post("/api/download/courses", json=params)
    assert response.status_code == 200
    assert not config_path.exists()

    course = response.json["courses"][0]
    assert course["live_id"] == "1234"
    assert client.post("/api/automation/config", json={
        **params, "courses": [{**course, "selected": True}],
    }).status_code == 200
    persisted = config.safe_read_config(str(config_path))
    assert persisted["101"]["download"] == "yes"
    assert persisted["DEFAULT"]["video_type"] == "teacher"
    assert client.get("/api/automation/config").json["courses"][0]["selected"] is True


def test_pause_resume_and_stop_all_control_the_serial_queue(monkeypatch, tmp_path):
    from threading import Event

    access = import_module("xduclassvideodownloader.web.access")
    app = import_module("xduclassvideodownloader.web.app")
    downloads = import_module("xduclassvideodownloader.web.downloads")
    monkeypatch.setattr(access, "AUTH_CONFIG_FILE", str(tmp_path / "auth.ini"))
    monkeypatch.setattr(app, "jobs", downloads.DownloadJobManager())
    monkeypatch.setattr(downloads, "get_auth_cookies", lambda **kwargs: {})
    started, check_pause, at_pause, resumed, check_stop = [Event() for _ in range(5)]
    completed = []

    def download(options, *, auth_cookies, observer, checkpoint):
        if options.live_id == "123":
            started.set()
            assert check_pause.wait(5)
            at_pause.set()
            checkpoint()
            resumed.set()
            assert check_stop.wait(5)
            checkpoint()
        completed.append(options.live_id)
        return True

    monkeypatch.setattr(downloads, "download_course", download)
    client = app.create_app({"TESTING": True}).test_client()
    response = client.post("/api/download/start", json={"mode": "batch", "courses": [
        {"live_id": "123"}, {"live_id": "456"},
    ]})
    job_id, _ = response.json["job_ids"]
    route = "/api/download/jobs/control"
    assert started.wait(3)
    try:
        assert client.post(route, json={"action": "pause"}).status_code == 200
        check_pause.set()
        assert at_pause.wait(3)
        assert not resumed.wait(0.1)
        jobs = client.get("/api/download/jobs").json["jobs"]
        assert [job["status"] for job in jobs] == ["paused", "pending"]
        assert client.post(route, json={"action": "resume"}).status_code == 200
        assert resumed.wait(3)
        assert client.post(route, json={"action": "stop"}).status_code == 200
        check_stop.set()
        app.jobs.get(job_id).thread.join(timeout=3)
        jobs = client.get("/api/download/jobs").json["jobs"]
        assert [job["status"] for job in jobs] == ["stopped", "stopped"]
        assert jobs[0]["errors"] == []
        assert completed == []
    finally:
        client.post(route, json={"action": "stop"})
        check_pause.set()
        check_stop.set()
