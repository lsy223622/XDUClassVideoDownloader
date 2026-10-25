"""Automation configuration helpers used by WebUI routes."""

import configparser
from typing import Any, Dict, List, Mapping, Optional

from ..core.config import AUTOMATION_CONFIG_FILE, safe_read_config, safe_write_config
from ..core.courses import default_term
from ..core.services import scan_term_courses
from ..core.utils import remove_invalid_chars
from ..core.validator import validate_term_params, validate_user_id


VIDEO_TYPE_CHOICES = {"both", "ppt", "teacher"}


def config_to_courses(config: configparser.ConfigParser) -> List[Dict[str, str]]:
    courses = []
    for section_name in config.sections():
        section = config[section_name]
        courses.append(
            {
                "section": section_name,
                "course_code": section.get("course_code", ""),
                "course_name": section.get("course_name", ""),
                "live_id": section.get("live_id", ""),
                "download": section.get("download", "yes").lower(),
                "selected": section.get("download", "yes").lower() == "yes",
            }
        )
    return courses


def automation_config_payload(
    config: configparser.ConfigParser, term_year: int, term_id: int
) -> Dict[str, Any]:
    default = config["DEFAULT"]
    return {
        "exists": True,
        "defaults": {
            "user_id": default.get("user_id", ""),
            "term_year": default.get("term_year", str(term_year)),
            "term_id": default.get("term_id", str(term_id)),
            "video_type": default.get("video_type", "both"),
        },
        "courses": config_to_courses(config),
    }


def validate_scan_params(user_id: str, term_year: int, term_id: int, video_type: str) -> None:
    if not validate_user_id(user_id):
        raise ValueError("用户 ID 格式无效")
    if not validate_term_params(term_year, term_id):
        raise ValueError("学期参数无效")
    if video_type not in VIDEO_TYPE_CHOICES:
        raise ValueError("视频类型无效")


def selected_sections_from_payload(payload: Mapping[str, Any]) -> List[str]:
    selected_sections = payload.get("selected_sections") or []
    if not isinstance(selected_sections, list):
        raise ValueError("课程选择格式无效")
    return [str(section) for section in selected_sections]


def read_automation_config():
    return safe_read_config(AUTOMATION_CONFIG_FILE)


def _course_config_section(course: Mapping[str, Any], download: str = "yes") -> Dict[str, str]:
    return {
        "course_code": str(course.get("courseCode", "")),
        "course_name": remove_invalid_chars(str(course.get("courseName", ""))),
        "live_id": str(course.get("id", "")),
        "download": download,
    }


def write_automation_config_from_scan(
    user_id: str,
    term_year: int,
    term_id: int,
    video_type: str,
    *,
    auth_cookies: Optional[Mapping[str, str]] = None,
) -> configparser.ConfigParser:
    validate_scan_params(user_id, term_year, term_id, video_type)
    courses = scan_term_courses(user_id, term_year, term_id, auth_cookies=auth_cookies)
    if not courses:
        raise ValueError("没有找到任何课程，请检查用户 ID 和学期参数")

    config = configparser.ConfigParser()
    config["DEFAULT"] = {
        "user_id": user_id,
        "term_year": str(term_year),
        "term_id": str(term_id),
        "video_type": video_type,
    }
    for course_id, course in courses.items():
        config[str(course_id)] = _course_config_section(course)
    safe_write_config(config, AUTOMATION_CONFIG_FILE)
    return config


def refresh_automation_config(
    base_config: configparser.ConfigParser,
    user_id: str,
    term_year: int,
    term_id: int,
    video_type: str,
    *,
    auth_cookies: Optional[Mapping[str, str]] = None,
) -> configparser.ConfigParser:
    validate_scan_params(user_id, term_year, term_id, video_type)
    courses = scan_term_courses(user_id, term_year, term_id, auth_cookies=auth_cookies)
    if not courses:
        raise ValueError("没有找到任何课程，请检查用户 ID 和学期参数")

    existing = {name: dict(base_config[name]) for name in base_config.sections()}
    new_config = configparser.ConfigParser()
    new_config["DEFAULT"] = {
        "user_id": user_id,
        "term_year": str(term_year),
        "term_id": str(term_id),
        "video_type": video_type,
    }
    for course_id, course in courses.items():
        section_name = str(course_id)
        old = existing.get(section_name, {})
        new_config[section_name] = _course_config_section(course, old.get("download", "yes"))
    safe_write_config(new_config, AUTOMATION_CONFIG_FILE)
    return new_config


__all__ = [
    "AUTOMATION_CONFIG_FILE",
    "VIDEO_TYPE_CHOICES",
    "automation_config_payload",
    "config_to_courses",
    "default_term",
    "read_automation_config",
    "refresh_automation_config",
    "selected_sections_from_payload",
    "validate_scan_params",
    "write_automation_config_from_scan",
]
