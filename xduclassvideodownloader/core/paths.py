"""Separate mutable runtime paths from read-only package resources."""

import os
import sys
from pathlib import Path
from typing import Optional, Union


PathPart = Union[str, os.PathLike]
_runtime_dir: Optional[Path] = None


def set_runtime_dir(path: Optional[PathPart]) -> None:
    """Set or clear the directory used for mutable application files."""

    global _runtime_dir
    _runtime_dir = None if path is None else Path(path).expanduser().resolve()


def get_app_dir() -> Path:
    """Return the directory for configuration, logs and downloaded files."""

    if _runtime_dir is not None:
        return _runtime_dir
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def get_app_path(*parts: PathPart) -> Path:
    """Resolve a mutable application path below :func:`get_app_dir`."""

    return get_app_dir().joinpath(*parts)


def get_package_dir() -> Path:
    """Return the installed package directory containing read-only resources."""

    return Path(__file__).resolve().parents[1]


def get_bundled_app_path(*parts: PathPart) -> Path:
    """Resolve a read-only resource from PyInstaller or the Python package."""

    bundled_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundled_root) if bundled_root else get_package_dir()
    return root.joinpath(*parts)
