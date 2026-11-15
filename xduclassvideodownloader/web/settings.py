"""Automation configuration helpers used by WebUI routes."""

import configparser
from typing import Any, Dict, List, Mapping

from ..core.auth import get_auth_cookies
from ..core.config import CaseSensitiveConfigParser, safe_read_config, safe_write_config
from ..core.services import scan_term_courses
from ..core.utils import remove_invalid_chars
from ..core.validator import validate_live_id, validate_term_params, validate_user_id


VIDEO_TYPE_CHOICES = {"both", "ppt", "teacher"}


def config_to_courses(config: configparser.ConfigParser) -> List[Dict[str, Any]]:
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


def read_automation_config(filename):
    return safe_read_config(filename)


def _course_config_section(course: Mapping[str, Any], download: str = "yes") -> Dict[str, str]:
    return {
        "course_code": str(course.get("courseCode", "")),
        "course_name": remove_invalid_chars(str(course.get("courseName", ""))),
        "live_id": str(course.get("id", "")),
        "download": download,
    }


def scan_automation_courses(user_id, term_year, term_id, video_type):
    validate_scan_params(user_id, term_year, term_id, video_type)
    courses = scan_term_courses(user_id, term_year, term_id, auth_cookies=get_auth_cookies(interactive=False))
    return [
        dict(section=str(course_id), selected=False, **_course_config_section(course, "no"))
        for course_id, course in courses.items()
    ]


def save_automation_courses(filename, user_id, term_year, term_id, video_type, courses):
    validate_scan_params(user_id, term_year, term_id, video_type)
    config = CaseSensitiveConfigParser()
    config["DEFAULT"] = {
        "user_id": user_id, "term_year": str(term_year),
        "term_id": str(term_id), "video_type": video_type,
    }
    if not isinstance(courses, list) or not courses:
        raise ValueError("请先读取配置或扫描课程")
    for course in courses:
        if not isinstance(course, dict):
            raise ValueError("课程数据无效")
        section = str(course["section"])
        live_id = str(course["live_id"])
        if not section or section == "DEFAULT" or any(char in section for char in "\r\n[]"):
            raise ValueError("课程数据无效")
        validate_live_id(live_id)
        course_name = str(course.get("course_name", ""))
        course_code = str(course.get("course_code", ""))
        if any(char in course_name or char in course_code for char in "\r\n"):
            raise ValueError("课程数据无效")
        config[section] = {
            "live_id": live_id, "course_name": course_name, "course_code": course_code,
            "download": "yes" if course.get("selected") is True else "no",
        }
    safe_write_config(config, filename, backup=True)
