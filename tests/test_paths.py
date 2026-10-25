"""Runtime and packaged-resource path contracts."""

import sys

from xduclassvideodownloader.core.paths import (
    get_app_dir,
    get_app_path,
    get_bundled_app_path,
    get_package_dir,
    set_runtime_dir,
)


def test_runtime_override_controls_mutable_files(tmp_path):
    set_runtime_dir(tmp_path)
    assert get_app_path("auth.ini") == tmp_path / "auth.ini"


def test_package_resources_do_not_follow_runtime_dir(tmp_path):
    set_runtime_dir(tmp_path)
    assert get_bundled_app_path("web", "static") != tmp_path / "web" / "static"


def test_frozen_runtime_uses_executable_parent(monkeypatch, tmp_path):
    exe = tmp_path / "XDUClassVideoDownloader.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    set_runtime_dir(None)
    assert get_app_dir() == tmp_path


def test_normal_runtime_defaults_to_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    set_runtime_dir(None)
    assert get_app_dir() == tmp_path


def test_package_directory_is_stable_when_runtime_dir_changes(tmp_path):
    set_runtime_dir(tmp_path)
    assert get_package_dir().name == "xduclassvideodownloader"
