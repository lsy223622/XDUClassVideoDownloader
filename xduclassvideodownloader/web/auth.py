"""WebUI authentication settings and redacted configuration payloads."""

import configparser
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from ..core import (
    clear_runtime_auth_cache,
    has_valid_auth_cookies,
    login_to_chaoxing,
    login_to_chaoxing_via_ids,
    set_runtime_auth_cookies,
)
from ..core.config import AUTH_CONFIG_FILE, REQUIRED_AUTH_COOKIES, CaseSensitiveConfigParser, safe_read_config, safe_write_config
from ..core.platform import FID
from ..core.utils import setup_logging


logger = setup_logging("webui")
AUTH_METHOD_CHOICES = {"ids", "chaoxing", "chaoxing_qr", "cookies"}


def auth_config_exists() -> bool:
    return Path(AUTH_CONFIG_FILE).exists()


def section_has_values(config: configparser.ConfigParser, section: str, keys: Iterable[str]) -> bool:
    if section not in config:
        return False
    return all(str(config[section].get(key, "")).strip() for key in keys)


def has_usable_auth(config: configparser.ConfigParser, auth_method: str) -> bool:
    if auth_method == "ids":
        return section_has_values(config, "IDS_CREDENTIALS", ("username", "password"))
    if auth_method == "chaoxing":
        return section_has_values(config, "CHAOXING_CREDENTIALS", ("username", "password"))
    if auth_method in {"cookies", "chaoxing_qr"}:
        cookies = {key: str(config["AUTH"].get(key, "")) for key in REQUIRED_AUTH_COOKIES} if "AUTH" in config else {}
        return has_valid_auth_cookies(cookies)
    return False


def auth_uid(config: configparser.ConfigParser, auth_method: str) -> str:
    if "AUTH" in config and str(config["AUTH"].get("UID", "")).strip():
        return str(config["AUTH"].get("UID", "")).strip()

    if auth_method not in {"ids", "chaoxing"} or not has_usable_auth(config, auth_method):
        return ""
    try:
        if auth_method == "ids":
            cookies = login_to_chaoxing_via_ids(
                str(config["IDS_CREDENTIALS"].get("username", "")),
                str(config["IDS_CREDENTIALS"].get("password", "")),
            )
        else:
            cookies = login_to_chaoxing(
                str(config["CHAOXING_CREDENTIALS"].get("username", "")),
                str(config["CHAOXING_CREDENTIALS"].get("password", "")),
            )
        if has_valid_auth_cookies(cookies):
            cookies["fid"] = FID
            set_runtime_auth_cookies(cookies)
        return str(cookies.get("UID", "")).strip()
    except Exception as exc:
        logger.debug("自动获取登录 UID 失败: %s", exc)
        return ""


def auth_config_payload() -> Dict[str, Any]:
    config = safe_read_config(AUTH_CONFIG_FILE) if auth_config_exists() else CaseSensitiveConfigParser()
    settings = config["SETTINGS"] if "SETTINGS" in config else {}
    auth_method = settings.get("auth_method", "ids") if hasattr(settings, "get") else "ids"
    auth_exists = auth_config_exists()
    auth_ready = auth_exists and has_usable_auth(config, auth_method)
    ids = config["IDS_CREDENTIALS"] if "IDS_CREDENTIALS" in config else {}
    chaoxing = config["CHAOXING_CREDENTIALS"] if "CHAOXING_CREDENTIALS" in config else {}
    cookies = config["AUTH"] if "AUTH" in config else {}
    return {
        "exists": auth_exists,
        "auth_method": auth_method,
        "auth_ready": auth_ready,
        "uid": auth_uid(config, auth_method),
        "save_auth_info": str(settings.get("save_auth_info", "true")).lower() == "true"
        if hasattr(settings, "get")
        else True,
        "ids": {
            "username": "",
            "password": "",
            "username_configured": bool(str(ids.get("username", "")).strip()),
            "password_configured": bool(str(ids.get("password", "")).strip()),
        },
        "chaoxing": {
            "username": "",
            "password": "",
            "username_configured": bool(str(chaoxing.get("username", "")).strip()),
            "password_configured": bool(str(chaoxing.get("password", "")).strip()),
        },
        "cookies": {
            "_d": "",
            "UID": "",
            "vc3": "",
            "_d_configured": bool(str(cookies.get("_d", "")).strip()),
            "UID_configured": bool(str(cookies.get("UID", "")).strip()),
            "vc3_configured": bool(str(cookies.get("vc3", "")).strip()),
        },
    }


def _replace_section(config: configparser.ConfigParser, section: str, values: Mapping[str, str]) -> None:
    if config.has_section(section):
        config.remove_section(section)
    config.add_section(section)
    for key, value in values.items():
        config[section][key] = value


def _payload_value_or_existing(values: Mapping[str, Any], existing: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    return str(existing.get(key, "")) if value is None else str(value)


def save_auth_payload(payload: Mapping[str, Any]) -> None:
    auth_method = str(payload.get("auth_method", "ids"))
    if auth_method not in AUTH_METHOD_CHOICES:
        raise ValueError("认证方式无效")
    save_auth_info = bool(payload.get("save_auth_info", True))

    config = safe_read_config(AUTH_CONFIG_FILE) if auth_config_exists() else CaseSensitiveConfigParser()
    existing_ids = dict(config["IDS_CREDENTIALS"]) if "IDS_CREDENTIALS" in config else {}
    existing_chaoxing = dict(config["CHAOXING_CREDENTIALS"]) if "CHAOXING_CREDENTIALS" in config else {}
    existing_auth = dict(config["AUTH"]) if "AUTH" in config else {}
    config["SETTINGS"] = {"auth_method": auth_method, "save_auth_info": str(save_auth_info)}
    for section in ("AUTH", "IDS_CREDENTIALS", "CHAOXING_CREDENTIALS"):
        if config.has_section(section):
            config.remove_section(section)
    if not save_auth_info:
        safe_write_config(config, AUTH_CONFIG_FILE, backup=True)
        clear_runtime_auth_cache()
        return

    if auth_method == "ids":
        values = payload.get("ids") or {}
        _replace_section(
            config,
            "IDS_CREDENTIALS",
            {
                "username": _payload_value_or_existing(values, existing_ids, "username"),
                "password": _payload_value_or_existing(values, existing_ids, "password"),
            },
        )
    elif auth_method == "chaoxing":
        values = payload.get("chaoxing") or {}
        _replace_section(
            config,
            "CHAOXING_CREDENTIALS",
            {
                "username": _payload_value_or_existing(values, existing_chaoxing, "username"),
                "password": _payload_value_or_existing(values, existing_chaoxing, "password"),
            },
        )
    else:
        values = payload.get("cookies") or {}
        auth_values = {
            key: _payload_value_or_existing(values, existing_auth, key) for key in REQUIRED_AUTH_COOKIES
        }
        if not has_valid_auth_cookies(auth_values):
            raise ValueError("Cookie 信息不完整")
        _replace_section(config, "AUTH", auth_values)

    safe_write_config(config, AUTH_CONFIG_FILE, backup=True)
    clear_runtime_auth_cache()


__all__ = [
    "AUTH_METHOD_CHOICES",
    "auth_config_exists",
    "auth_config_payload",
    "auth_uid",
    "has_usable_auth",
    "save_auth_payload",
    "section_has_values",
]
