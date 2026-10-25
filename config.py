"""Compatibility exports for the package configuration and auth services."""

from xduclassvideodownloader.core.auth import get_auth_cookies as _get_auth_cookies
from xduclassvideodownloader.core.config import *  # noqa: F401,F403


def get_auth_cookies(fid=None, *, force_refresh: bool = False):
    """Preserve the legacy optional ``fid`` argument while using Core auth."""

    return _get_auth_cookies(force_refresh=force_refresh, fid=fid)


__all__ = [
    "AUTH_CONFIG_FILE",
    "AUTOMATION_CONFIG_FILE",
    "CaseSensitiveConfigParser",
    "REQUIRED_AUTH_COOKIES",
    "create_initial_config",
    "format_auth_cookies",
    "get_auth_cookies",
    "has_valid_auth_cookies",
    "safe_read_config",
    "safe_write_config",
    "update_course_config",
    "update_existing_config",
    "validate_config_structure",
]
