"""Characterization tests for the existing 5.0 entrypoints and contracts."""

import sys

import pytest


def test_single_cli_help_does_not_require_auth(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["XDUClassVideoDownloader.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        import XDUClassVideoDownloader as entry

        entry.parse_main_arguments()
    assert exc.value.code == 0


def test_automation_cli_help_does_not_require_auth(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["Automation.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        import Automation as entry

        entry.parse_automation_arguments()
    assert exc.value.code == 0


def test_webui_default_host_and_port():
    import WebUI

    assert WebUI.DEFAULT_WEBUI_HOST == "127.0.0.1"
    assert WebUI.DEFAULT_WEBUI_PORT == 5050


def test_auth_cookie_contract_is_case_sensitive():
    from config import REQUIRED_AUTH_COOKIES

    assert REQUIRED_AUTH_COOKIES == ("_d", "UID", "vc3")


def test_course_directory_and_filename_contract():
    from downloader import _build_base_filename
    from utils import remove_invalid_chars

    course_name = remove_invalid_chars("数据结构:实验")
    assert course_name == "数据结构_实验"
    assert _build_base_filename("CS101", course_name, 2026, 9, 22, 3, "二", 1) == (
        "CS101数据结构_实验2026年9月22日第3周星期二第1节"
    )


def test_automation_course_update_preserves_disabled_selection():
    import configparser

    from config import update_course_config

    config = configparser.ConfigParser()
    config["101"] = {
        "course_code": "OLD",
        "course_name": "旧名称",
        "live_id": "9",
        "download": "no",
    }
    updated = update_course_config(
        config,
        {
            101: {"courseCode": "NEW", "courseName": "新名称", "id": 10},
        },
    )

    assert updated is True
    assert config["101"]["download"] == "no"


def test_update_check_failure_is_non_fatal(monkeypatch):
    import api

    monkeypatch.setattr(
        api,
        "fetch_update_info",
        lambda: {"ok": False, "allow_start": True, "error_kind": "network"},
    )

    assert api.check_update() is True


def test_parse_week_ranges_preserves_existing_contract():
    from xduclassvideodownloader.core.utils import parse_week_ranges

    assert parse_week_ranges("1-3,7,9-11") == {1, 2, 3, 7, 9, 10, 11}


def test_remove_invalid_chars_keeps_filename_contract():
    from xduclassvideodownloader.core.utils import remove_invalid_chars

    value = remove_invalid_chars("课程:A/B*?")
    assert "/" not in value
    assert "*" not in value
    assert "?" not in value
