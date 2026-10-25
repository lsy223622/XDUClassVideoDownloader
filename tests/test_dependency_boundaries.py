"""Static dependency-direction checks for the package architecture."""

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "xduclassvideodownloader"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            yield module, tuple(alias.name for alias in node.names)


def test_core_never_imports_web_or_flask():
    forbidden = {"flask", "xduclassvideodownloader.web"}
    for path in (PACKAGE_ROOT / "core").glob("*.py"):
        for module, names in _imports(path):
            assert module not in forbidden
            assert not module.startswith("xduclassvideodownloader.web")


def test_web_does_not_import_legacy_root_modules():
    forbidden = {"XDUClassVideoDownloader", "Automation", "WebUI", "api", "config", "downloader", "utils", "validator"}
    for path in (PACKAGE_ROOT / "web").glob("*.py"):
        for module, names in _imports(path):
            assert module.split(".", 1)[0] not in forbidden


def test_web_and_cli_do_not_import_private_core_names():
    for package_name in ("web", "cli"):
        for path in (PACKAGE_ROOT / package_name).glob("*.py"):
            for module, names in _imports(path):
                if not module.startswith("xduclassvideodownloader.core") or not names:
                    continue
                assert all(not name.startswith("_") for name in names if name != "*")
