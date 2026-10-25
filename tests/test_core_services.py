"""Stable Core service facade contracts."""

import configparser
import time


def test_default_term_matches_existing_semester_rules():
    from xduclassvideodownloader.core.courses import default_term

    september = time.struct_time((2026, 9, 1, 0, 0, 0, 0, 0, -1))
    january = time.struct_time((2026, 1, 1, 0, 0, 0, 0, 0, -1))
    april = time.struct_time((2026, 4, 1, 0, 0, 0, 0, 0, -1))

    assert default_term(september) == (2026, 1)
    assert default_term(january) == (2025, 1)
    assert default_term(april) == (2025, 2)


def test_selected_sections_do_not_mutate_persisted_config(monkeypatch):
    from xduclassvideodownloader.core import services

    config = configparser.ConfigParser()
    config["DEFAULT"] = {"video_type": "both"}
    config["CourseA"] = {"live_id": "1", "download": "yes"}
    config["CourseB"] = {"live_id": "2", "download": "no"}
    original = [(section, dict(config[section])) for section in config.sections()]
    captured = {}

    monkeypatch.setattr(
        services,
        "process_all_courses",
        lambda runtime_config, video_type, auth_cookies: captured.update(
            config=runtime_config, video_type=video_type, auth_cookies=auth_cookies
        )
        or True,
    )

    assert services.download_courses(
        config,
        selected_sections=["CourseB"],
        video_type="teacher",
        auth_cookies={"_d": "a", "UID": "b", "vc3": "c"},
    )
    assert [(section, dict(config[section])) for section in config.sections()] == original
    assert captured["config"]["CourseA"]["download"] == "no"
    assert captured["config"]["CourseB"]["download"] == "yes"
    assert captured["video_type"] == "teacher"


def test_download_course_passes_auth_and_parsed_skip_weeks(monkeypatch):
    from xduclassvideodownloader.core import services

    captured = {}
    monkeypatch.setattr(
        services,
        "download_course_videos",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs) or True,
    )

    assert services.download_course(
        services.CourseDownloadOptions(
            live_id="12345", single=1, merge=False, video_type="ppt", skip_weeks="2,4-5"
        ),
        auth_cookies={"_d": "a", "UID": "b", "vc3": "c"},
    )
    assert captured["args"][:4] == (12345, 1, False, "ppt")
    assert captured["args"][4] == {2, 4, 5}
    assert captured["kwargs"]["auth_cookies"]["UID"] == "b"


def test_scan_term_courses_passes_explicit_auth(monkeypatch):
    from xduclassvideodownloader.core import services

    captured = {}
    monkeypatch.setattr(
        services,
        "scan_courses",
        lambda user_id, term_year, term_id, auth_cookies: captured.update(
            values=(user_id, term_year, term_id, auth_cookies)
        )
        or {1: {"courseName": "课程"}},
    )

    assert services.scan_term_courses(
        "123456", 2026, 1, auth_cookies={"_d": "a", "UID": "b", "vc3": "c"}
    ) == {1: {"courseName": "课程"}}
    assert captured["values"][3]["_d"] == "a"
