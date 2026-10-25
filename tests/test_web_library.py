"""Web media-library grouping and traversal contracts."""

from importlib import import_module


def test_library_groups_tracks_subtitles_and_rejects_escape(monkeypatch, tmp_path):
    app_module = import_module("xduclassvideodownloader.web.app")
    library = import_module("xduclassvideodownloader.web.library")
    app_dir = tmp_path / "app"
    course_dir = app_dir / "2026年秋" / "数据结构"
    course_dir.mkdir(parents=True)
    (course_dir / "数据结构-2026年9月1日第1周星期一第1-2节-pptVideo.mp4").write_bytes(b"ppt")
    (course_dir / "数据结构-2026年9月1日第1周星期一第1-2节-teacherTrack.ts").write_bytes(b"teacher")
    (course_dir / "数据结构-2026年9月1日第1周星期一第1-2节.srt").write_text("subtitle", encoding="utf-8")

    payload = library.index_local_library(app_dir)

    assert len(payload["courses"]) == 1
    item = payload["courses"][0]["items"][0]
    assert set(item["tracks"]) == {"pptVideo", "teacherTrack"}
    assert item["subtitle_url"].endswith(".srt")

    monkeypatch.setattr(app_module, "APP_DIR", app_dir)
    with app_module.create_app({"TESTING": True}).test_request_context("/media/../outside.mp4"):
        result = app_module.media("../outside.mp4")
    assert result[1] == 403
