"""Run the Windows build script with a local PyInstaller substitute."""

import os
from pathlib import Path
import shutil
import subprocess
import venv

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows batch script")


@pytest.fixture
def build_root(tmp_path):
    root = tmp_path / "打包 test"
    root.mkdir()
    shutil.copy2(Path(__file__).resolve().parents[1] / "build.bat", root / "build.bat")
    venv.EnvBuilder(with_pip=False).create(root / ".venv")
    (root / "xduclassvideodownloader").mkdir()
    (root / "xduclassvideodownloader" / "_version.py").write_text(
        '__version__ = "5.1.2"\n', encoding="utf-8",
    )
    (root / "dist").mkdir()
    (root / "PyInstaller.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "program = Path(sys.argv[-1]).stem\n"
        "with Path('calls.txt').open('a') as calls: calls.write(program + '\\n')\n"
        "if Path('fail-' + program).exists(): sys.exit(1)\n"
        "staging = Path(sys.argv[sys.argv.index('--distpath') + 1])\n"
        "(staging / (program + '.exe')).write_bytes(program.encode())\n"
        "if program == 'WebUI' and Path('late-collision').exists():\n"
        "    Path('dist/WebUI_v5.1.2-beta.exe').write_bytes(b'late program')\n",
        encoding="utf-8",
    )
    return root


def run_build(root):
    return subprocess.run(
        ["cmd.exe", "/d", "/c", "build.bat"], cwd=root, input="\n",
        capture_output=True, text=True, errors="replace", timeout=30,
    )


def test_builds_three_programs_with_versioned_names(build_root):
    previous = build_root / "dist" / "WebUI_v5.0.0-beta.exe"
    previous.write_bytes(b"previous release")
    unversioned = build_root / "dist" / "WebUI.exe"
    unversioned.write_bytes(b"existing program")

    result = run_build(build_root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (build_root / "calls.txt").read_text().splitlines() == [
        "XDUClassVideoDownloader", "Automation", "WebUI",
    ]
    for program in ("XDUClassVideoDownloader", "Automation", "WebUI"):
        assert (build_root / "dist" / f"{program}_v5.1.2-beta.exe").read_bytes() == program.encode()
    assert previous.read_bytes() == b"previous release"
    assert unversioned.read_bytes() == b"existing program"


@pytest.mark.parametrize("program", ["XDUClassVideoDownloader", "Automation", "WebUI"])
def test_existing_version_stops_before_building(build_root, program):
    released = build_root / "dist" / f"{program}_v5.1.2-beta.exe"
    released.write_bytes(b"released")

    assert run_build(build_root).returncode != 0
    assert not (build_root / "calls.txt").exists()
    assert released.read_bytes() == b"released"


def test_build_failure_stops_before_publishing(build_root):
    (build_root / "fail-Automation").touch()

    assert run_build(build_root).returncode != 0
    assert (build_root / "calls.txt").read_text().splitlines() == ["XDUClassVideoDownloader", "Automation"]
    assert not list((build_root / "dist").iterdir())


def test_target_created_during_build_is_not_overwritten(build_root):
    (build_root / "late-collision").touch()

    assert run_build(build_root).returncode != 0
    assert (build_root / "dist" / "WebUI_v5.1.2-beta.exe").read_bytes() == b"late program"
