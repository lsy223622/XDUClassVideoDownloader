"""Core orchestration for single-course and batch operations."""

import configparser
from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, Optional

from .auth import get_auth_cookies
from .courses import default_term
from .downloader import download_course_videos, process_all_courses
from .models import CourseDownloadOptions
from .platform import scan_courses
from .platform import check_update as _platform_check_update
from .utils import parse_week_ranges
from .validator import validate_download_parameters


def _resolve_auth(auth_cookies: Optional[Mapping[str, str]]) -> Dict[str, str]:
    return dict(auth_cookies) if auth_cookies is not None else get_auth_cookies()


def check_update() -> bool:
    return _platform_check_update()


def scan_term_courses(
    user_id: str,
    term_year: int,
    term_id: int,
    *,
    auth_cookies: Optional[Mapping[str, str]] = None,
) -> Dict[int, Dict[str, Any]]:
    return scan_courses(
        user_id,
        term_year,
        term_id,
        auth_cookies=_resolve_auth(auth_cookies),
    )


def download_course(
    options: CourseDownloadOptions,
    *,
    auth_cookies: Optional[Mapping[str, str]] = None,
) -> bool:
    validated_live_id, validated_single, validated_video_type = validate_download_parameters(
        options.live_id, options.single, options.video_type
    )
    skip_weeks = parse_week_ranges(options.skip_weeks)
    return download_course_videos(
        validated_live_id,
        validated_single,
        options.merge,
        validated_video_type,
        skip_weeks,
        auth_cookies=_resolve_auth(auth_cookies),
    )


def download_courses(
    config: configparser.ConfigParser,
    *,
    selected_sections: Optional[Iterable[str]] = None,
    video_type: Optional[str] = None,
    auth_cookies: Optional[Mapping[str, str]] = None,
) -> bool:
    """Download selected courses from an in-memory copy of automation config."""

    runtime_config = deepcopy(config)
    if selected_sections is not None:
        selected = {str(section) for section in selected_sections}
        for section in runtime_config.sections():
            runtime_config[section]["download"] = "yes" if section in selected else "no"

    resolved_video_type = video_type or runtime_config["DEFAULT"].get("video_type", "both")
    return process_all_courses(
        runtime_config,
        resolved_video_type,
        _resolve_auth(auth_cookies),
    )


__all__ = [
    "CourseDownloadOptions",
    "check_update",
    "default_term",
    "download_course",
    "download_courses",
    "scan_term_courses",
]
