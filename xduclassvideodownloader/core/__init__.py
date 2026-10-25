"""The intentionally small public Core import facade."""

from .._version import __version__
from .auth import (
    ChaoxingQRLoginSession,
    QRLoginResult,
    clear_runtime_auth_cache,
    get_auth_cookies,
    has_valid_auth_cookies,
    login_to_chaoxing,
    login_to_chaoxing_via_ids,
    set_runtime_auth_cookies,
)
from .courses import default_term
from .models import CourseDownloadOptions
from .services import check_update, download_course, download_courses, scan_term_courses

__all__ = [
    "ChaoxingQRLoginSession",
    "CourseDownloadOptions",
    "QRLoginResult",
    "__version__",
    "clear_runtime_auth_cache",
    "check_update",
    "default_term",
    "download_course",
    "download_courses",
    "get_auth_cookies",
    "has_valid_auth_cookies",
    "login_to_chaoxing",
    "login_to_chaoxing_via_ids",
    "scan_term_courses",
    "set_runtime_auth_cookies",
]
