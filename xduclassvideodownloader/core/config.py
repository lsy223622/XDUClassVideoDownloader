"""Network-free configuration persistence for the application Core."""

import configparser
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .paths import get_app_path
from .utils import handle_exception, remove_invalid_chars, setup_logging
from .validator import validate_term_params, validate_user_id


logger = setup_logging("config")

AUTOMATION_CONFIG_FILE = str(get_app_path("automation_config.ini"))
AUTH_CONFIG_FILE = str(get_app_path("auth.ini"))
REQUIRED_AUTH_COOKIES = ("_d", "UID", "vc3")


class CaseSensitiveConfigParser(configparser.ConfigParser):
    """Keep configuration key casing, including authentication cookie names."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("interpolation", None)
        super().__init__(*args, **kwargs)

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def has_valid_auth_cookies(cookies: Optional[Mapping[str, str]]) -> bool:
    """Return whether all required cookie keys contain non-empty values."""

    return isinstance(cookies, Mapping) and all(cookies.get(key) for key in REQUIRED_AUTH_COOKIES)


def safe_write_config(
    config: configparser.ConfigParser, filename: str, backup: bool = False
) -> None:
    """Atomically write an INI file and optionally save a timestamped backup."""

    filepath = Path(filename)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if backup and filepath.exists():
        logs_dir = get_app_path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        backup_filename = f"{filepath.stem}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}{filepath.suffix}"
        backup_path = logs_dir / backup_filename
        try:
            shutil.copy2(filepath, backup_path)
            logger.info("配置文件备份已创建: %s", backup_path)
        except OSError as exc:
            logger.warning("无法创建配置文件备份: %s", exc)

    temp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(filepath.parent),
            prefix=f".{filepath.name}.tmp",
        ) as temp_file:
            config.write(temp_file)
            temp_name = temp_file.name
        shutil.move(temp_name, str(filepath))
        logger.info("配置文件写入成功: %s", filepath)
    except Exception as exc:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise OSError(f"写入配置文件失败 {filename}: {exc}") from exc


def safe_read_config(filename: str) -> CaseSensitiveConfigParser:
    """Read an INI file while preserving the original key casing."""

    filepath = Path(filename)
    if not filepath.exists():
        raise FileNotFoundError(f"配置文件不存在: {filename}")

    config = CaseSensitiveConfigParser()
    try:
        config.read(str(filepath), encoding="utf-8")
        logger.debug("成功读取配置文件: %s", filepath)
        return config
    except configparser.Error:
        logger.exception("配置文件格式错误")
        raise
    except Exception as exc:
        logger.error("读取配置文件失败: %s", exc)
        raise


def format_auth_cookies(auth_cookies: Mapping[str, str]) -> str:
    """Format only the three required cookie values for platform requests."""

    missing = [key for key in REQUIRED_AUTH_COOKIES if not auth_cookies.get(key)]
    if missing:
        raise ValueError(f"缺少必要的认证信息: {missing[0]}")
    fid_value = auth_cookies.get("fid", "")
    return f"fid={fid_value}; _d={auth_cookies['_d']}; UID={auth_cookies['UID']}; vc3={auth_cookies['vc3']}"


def update_course_config(
    config: configparser.ConfigParser, new_courses: Mapping[Any, Dict[str, Any]]
) -> bool:
    """Merge scanned courses while preserving existing download selections."""

    config_updated = False
    existing_courses = {section: dict(config[section]) for section in config.sections()}

    for course_id, course in new_courses.items():
        course_id_str = str(course_id)
        course_name = remove_invalid_chars(course["courseName"])
        if course_id_str not in config.sections():
            logger.info("添加新课程：%s - %s", course_id_str, course["courseName"])
            config[course_id_str] = {
                "course_code": course["courseCode"],
                "course_name": course_name,
                "live_id": str(course["id"]),
                "download": "yes",
            }
            config_updated = True
            continue

        existing_course = existing_courses[course_id_str]
        if (
            existing_course.get("course_code") != course["courseCode"]
            or existing_course.get("course_name") != course_name
            or existing_course.get("live_id") != str(course["id"])
        ):
            logger.info("更新课程信息：%s - %s", course_id_str, course["courseName"])
            config[course_id_str] = {
                "course_code": course["courseCode"],
                "course_name": course_name,
                "live_id": str(course["id"]),
                "download": existing_course.get("download", "yes"),
            }
            config_updated = True

    return config_updated


def validate_config_structure(config: configparser.ConfigParser) -> bool:
    """Validate the required default automation settings."""

    if "DEFAULT" not in config:
        raise ValueError("配置文件缺少 DEFAULT 区域")
    for key in ("user_id", "term_year", "term_id"):
        if key not in config["DEFAULT"]:
            raise configparser.Error(f"配置文件缺少必要的配置项: {key}")
    return True


def _course_sections(courses: Mapping[Any, Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    return {
        str(course_id): {
            "course_code": course["courseCode"],
            "course_name": remove_invalid_chars(course["courseName"]),
            "live_id": str(course["id"]),
            "download": "yes",
        }
        for course_id, course in courses.items()
    }


def create_initial_config(
    args: Any,
    default_year: int,
    default_term: int,
    config_file: str,
    *,
    courses: Optional[Mapping[Any, Dict[str, Any]]] = None,
) -> bool:
    """Create automation configuration from already-scanned course data."""

    try:
        user_id = args.uid or input("请输入用户ID：").strip()
        if not validate_user_id(user_id):
            print("用户ID格式无效")
            return False

        term_year = args.year if args.year else default_year
        term_id = args.term if args.term else default_term
        video_type = args.video_type if args.video_type else "both"
        if not validate_term_params(term_year, term_id):
            print("学期参数无效")
            return False
        if courses is None:
            raise ValueError("create_initial_config requires scanned courses")

        config = CaseSensitiveConfigParser()
        config["DEFAULT"] = {
            "user_id": str(user_id),
            "term_year": str(term_year),
            "term_id": str(term_id),
            "video_type": video_type,
        }
        for section, values in _course_sections(courses).items():
            config[section] = values
        safe_write_config(config, config_file)
        print(f"配置文件已生成，包含 {len(courses)} 门课程")
        return True
    except Exception as exc:
        print(handle_exception(exc, "创建配置文件失败"))
        return False


def update_existing_config(
    args: Any,
    default_year: int,
    default_term: int,
    config: configparser.ConfigParser,
    config_file: str,
    *,
    courses: Optional[Mapping[Any, Dict[str, Any]]] = None,
) -> bool:
    """Update automation settings from already-scanned course data."""

    try:
        user_id = args.uid or config["DEFAULT"].get("user_id", "")
        term_year = args.year if args.year else int(config["DEFAULT"].get("term_year", default_year))
        term_id = args.term if args.term else int(config["DEFAULT"].get("term_id", default_term))
        video_type = args.video_type if args.video_type else config["DEFAULT"].get("video_type", "both")
        if not validate_user_id(user_id) or not validate_term_params(term_year, term_id):
            print("配置文件中的参数无效")
            return False
        if courses is None:
            raise ValueError("update_existing_config requires scanned courses")

        update_course_config(config, courses)
        config["DEFAULT"]["user_id"] = str(user_id)
        config["DEFAULT"]["video_type"] = video_type
        config["DEFAULT"]["term_year"] = str(term_year)
        config["DEFAULT"]["term_id"] = str(term_id)
        safe_write_config(config, config_file)
        return True
    except Exception as exc:
        print(handle_exception(exc, "更新配置失败"))
        return False


__all__ = [
    "AUTH_CONFIG_FILE",
    "AUTOMATION_CONFIG_FILE",
    "CaseSensitiveConfigParser",
    "REQUIRED_AUTH_COOKIES",
    "create_initial_config",
    "format_auth_cookies",
    "has_valid_auth_cookies",
    "safe_read_config",
    "safe_write_config",
    "update_course_config",
    "update_existing_config",
    "validate_config_structure",
]
