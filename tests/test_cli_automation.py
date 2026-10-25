"""Semester automation CLI contracts."""

from argparse import Namespace


def test_automation_uses_core_default_term(monkeypatch, tmp_path):
    from xduclassvideodownloader.cli import automation

    captured = {}
    monkeypatch.setattr(automation, "check_update", lambda: True)
    monkeypatch.setattr(automation, "get_auth_cookies", lambda: {"_d": "a", "UID": "b", "vc3": "c"})
    monkeypatch.setattr(automation, "default_term", lambda: (2026, 1))
    monkeypatch.setattr(
        automation,
        "scan_term_courses",
        lambda user_id, term_year, term_id, auth_cookies: captured.update(
            scan=(user_id, term_year, term_id, auth_cookies)
        )
        or {101: {"courseCode": "CS101", "courseName": "数据结构", "id": 10}},
    )
    monkeypatch.setattr(
        automation,
        "download_courses",
        lambda config, selected_sections, video_type, auth_cookies: captured.update(
            download=(config, selected_sections, video_type, auth_cookies)
        )
        or True,
    )

    args = Namespace(uid="123456", year=None, term=None, video_type=None, debug=False)
    assert automation.main(args=args, config_file=str(tmp_path / "automation_config.ini")) is True
    assert captured["scan"][1:3] == (2026, 1)


def test_automation_preserves_disabled_courses_during_update(monkeypatch, tmp_path):
    from xduclassvideodownloader.cli import automation
    from xduclassvideodownloader.core.config import CaseSensitiveConfigParser, safe_write_config, safe_read_config

    config_file = tmp_path / "automation_config.ini"
    existing = CaseSensitiveConfigParser()
    existing["DEFAULT"] = {"user_id": "123456", "term_year": "2025", "term_id": "2", "video_type": "both"}
    existing["101"] = {"course_code": "OLD", "course_name": "旧名称", "live_id": "9", "download": "no"}
    safe_write_config(existing, str(config_file))
    captured = {}
    monkeypatch.setattr(automation, "check_update", lambda: True)
    monkeypatch.setattr(automation, "get_auth_cookies", lambda: {"_d": "a", "UID": "b", "vc3": "c"})
    monkeypatch.setattr(automation, "scan_term_courses", lambda *args, **kwargs: {101: {"courseCode": "NEW", "courseName": "新名称", "id": 10}})
    monkeypatch.setattr(
        automation,
        "download_courses",
        lambda config, selected_sections, video_type, auth_cookies: captured.update(config=config) or True,
    )

    args = Namespace(uid=None, year=None, term=None, video_type=None, debug=False)
    assert automation.main(args=args, config_file=str(config_file)) is True
    assert captured["config"]["101"]["download"] == "no"
    assert safe_read_config(str(config_file))["101"]["download"] == "no"
