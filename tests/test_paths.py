"""Runtime and packaged-resource path contracts."""

import sys

from xduclassvideodownloader.core import paths
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
    set_runtime_dir(tmp_path / "_MEI12345")
    assert get_app_dir() == tmp_path


def test_normal_runtime_defaults_to_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    set_runtime_dir(None)
    assert get_app_dir() == tmp_path


def test_package_directory_is_stable_when_runtime_dir_changes(tmp_path):
    set_runtime_dir(tmp_path)
    assert get_package_dir().name == "xduclassvideodownloader"


def test_frozen_resources_use_package_directory_inside_bundle(monkeypatch, tmp_path):
    bundled_root = tmp_path / "_MEI12345"
    package_dir = bundled_root / "xduclassvideodownloader"
    index = package_dir / "web" / "static" / "index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<html>WebUI</html>", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled_root), raising=False)
    monkeypatch.setattr(paths, "__file__", str(package_dir / "core" / "paths.py"))

    assert get_bundled_app_path("web", "static", "index.html").read_text(encoding="utf-8") == "<html>WebUI</html>"
