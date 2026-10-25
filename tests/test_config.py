"""Network-free Core configuration persistence contracts."""

import configparser


def test_safe_write_and_read_round_trip(tmp_path):
    from xduclassvideodownloader.core.config import (
        CaseSensitiveConfigParser,
        safe_read_config,
        safe_write_config,
    )

    target = tmp_path / "automation_config.ini"
    cfg = CaseSensitiveConfigParser()
    cfg["DEFAULT"] = {"user_id": "123", "video_type": "both"}
    safe_write_config(cfg, str(target))
    loaded = safe_read_config(str(target))

    assert loaded["DEFAULT"]["user_id"] == "123"
    assert isinstance(loaded, CaseSensitiveConfigParser)


def test_auth_cookie_keys_keep_case(tmp_path):
    from xduclassvideodownloader.core.config import (
        CaseSensitiveConfigParser,
        safe_read_config,
        safe_write_config,
    )

    target = tmp_path / "auth.ini"
    cfg = CaseSensitiveConfigParser()
    cfg["AUTH"] = {"_d": "a", "UID": "b", "vc3": "c"}
    safe_write_config(cfg, str(target))
    loaded = safe_read_config(str(target))

    assert set(loaded["AUTH"]) >= {"_d", "UID", "vc3"}


def test_safe_write_creates_backup_in_runtime_logs(tmp_path):
    from xduclassvideodownloader.core.config import (
        CaseSensitiveConfigParser,
        safe_write_config,
    )
    from xduclassvideodownloader.core.paths import set_runtime_dir

    set_runtime_dir(tmp_path)
    target = tmp_path / "auth.ini"
    target.write_text("[AUTH]\nUID=old\n", encoding="utf-8")
    cfg = CaseSensitiveConfigParser()
    cfg["AUTH"] = {"UID": "new"}
    safe_write_config(cfg, str(target), backup=True)

    assert list((tmp_path / "logs").glob("auth.bak.*.ini"))


def test_update_course_config_preserves_disabled_selection():
    from xduclassvideodownloader.core.config import update_course_config

    cfg = configparser.ConfigParser()
    cfg["101"] = {
        "course_code": "OLD",
        "course_name": "旧名称",
        "live_id": "9",
        "download": "no",
    }

    assert update_course_config(
        cfg,
        {101: {"courseCode": "NEW", "courseName": "新名称", "id": 10}},
    )
    assert cfg["101"]["download"] == "no"


def test_create_initial_config_persists_scanned_courses_without_network(tmp_path):
    from types import SimpleNamespace

    from xduclassvideodownloader.core.config import (
        create_initial_config,
        safe_read_config,
    )

    target = tmp_path / "automation_config.ini"
    args = SimpleNamespace(uid="123456", year=None, term=None, video_type=None)
    assert create_initial_config(
        args,
        2026,
        1,
        str(target),
        courses={101: {"courseCode": "CS101", "courseName": "数据结构", "id": 10}},
    )
    loaded = safe_read_config(str(target))

    assert loaded["DEFAULT"]["user_id"] == "123456"
    assert loaded["101"]["download"] == "yes"
