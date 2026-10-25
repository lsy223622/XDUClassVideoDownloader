"""Compatibility shim for the XDUClassVideoDownloader 5.x utilities."""

from xduclassvideodownloader.core.paths import (  # noqa: F401
    get_app_dir,
    get_app_path,
    set_runtime_dir,
)
from xduclassvideodownloader.core.paths import get_bundled_app_path as _get_core_bundled_app_path
from xduclassvideodownloader.core.utils import *  # noqa: F401,F403,E402


def get_bundled_app_path(*parts):
    """Map the legacy WebUI resource name to the packaged static resources."""

    if parts and str(parts[0]) == "webui":
        return _get_core_bundled_app_path("web", "static", *parts[1:])
    return _get_core_bundled_app_path(*parts)
