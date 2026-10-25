"""WebUI access policy and password helpers."""

import hashlib
import hmac
import ipaddress
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable, List, Optional, Union

from ..core.config import AUTH_CONFIG_FILE, CaseSensitiveConfigParser, safe_write_config
from ..core.utils import setup_logging


logger = setup_logging("webui")
DEFAULT_WEBUI_HOST = "127.0.0.1"
WEBUI_AUTH_SECTION = "WEBUI"
WEBUI_PASSWORD_KEY = "password_hash"
WEBUI_LEGACY_PASSWORD_KEY = "password"
WEBUI_ALLOW_PASSWORD_CHANGE_KEY = "allow_password_change"
WEBUI_BIND_HOST_KEY = "bind_host"
WEBUI_ALLOWED_CLIENTS_KEY = "allowed_clients"
WEBUI_PBKDF2_ITERATIONS = 120_000


def read_auth_config() -> CaseSensitiveConfigParser:
    config = CaseSensitiveConfigParser()
    if Path(AUTH_CONFIG_FILE).exists():
        config.read(AUTH_CONFIG_FILE, encoding="utf-8")
    return config


def configured_webui_host() -> str:
    config = read_auth_config()
    if WEBUI_AUTH_SECTION not in config:
        return DEFAULT_WEBUI_HOST
    host = str(config[WEBUI_AUTH_SECTION].get(WEBUI_BIND_HOST_KEY, "")).strip()
    return host or DEFAULT_WEBUI_HOST


def configured_allowed_clients() -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
    config = read_auth_config()
    if WEBUI_AUTH_SECTION not in config:
        return []
    raw_value = str(config[WEBUI_AUTH_SECTION].get(WEBUI_ALLOWED_CLIENTS_KEY, "")).strip()
    if not raw_value:
        return []

    networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
    for item in re.split(r"[\s,]+", raw_value):
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError as exc:
            raise ValueError(f"WEBUI.{WEBUI_ALLOWED_CLIENTS_KEY} 包含无效网段: {item}") from exc
    return networks


def client_ip_allowed(remote_addr: Optional[str]) -> bool:
    allowed_clients = configured_allowed_clients()
    if not allowed_clients:
        return True
    if not remote_addr:
        return False
    try:
        client_ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    return any(client_ip in network for network in allowed_clients)


def set_auth_config_private_permissions() -> None:
    if os.name != "posix":
        return
    try:
        os.chmod(AUTH_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning("无法设置认证文件权限: %s", exc)


def hash_webui_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, WEBUI_PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${WEBUI_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_webui_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if not stored.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored)
    try:
        _, iterations_text, salt_hex, digest_hex = stored.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_text))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def get_webui_password_hash(config: Optional[CaseSensitiveConfigParser] = None) -> str:
    config = config or read_auth_config()
    if WEBUI_AUTH_SECTION not in config:
        return ""
    section = config[WEBUI_AUTH_SECTION]
    return str(section.get(WEBUI_PASSWORD_KEY, "") or section.get(WEBUI_LEGACY_PASSWORD_KEY, "")).strip()


def webui_password_change_allowed(config: Optional[CaseSensitiveConfigParser] = None) -> bool:
    config = config or read_auth_config()
    if WEBUI_AUTH_SECTION not in config:
        return True
    return str(config[WEBUI_AUTH_SECTION].get(WEBUI_ALLOW_PASSWORD_CHANGE_KEY, "true")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def save_webui_password(password: str) -> bool:
    config = read_auth_config()
    if password:
        if not config.has_section(WEBUI_AUTH_SECTION):
            config.add_section(WEBUI_AUTH_SECTION)
        config[WEBUI_AUTH_SECTION][WEBUI_PASSWORD_KEY] = hash_webui_password(password)
        if WEBUI_LEGACY_PASSWORD_KEY in config[WEBUI_AUTH_SECTION]:
            del config[WEBUI_AUTH_SECTION][WEBUI_LEGACY_PASSWORD_KEY]
        enabled = True
    else:
        if config.has_section(WEBUI_AUTH_SECTION):
            config[WEBUI_AUTH_SECTION].pop(WEBUI_PASSWORD_KEY, None)
            config[WEBUI_AUTH_SECTION].pop(WEBUI_LEGACY_PASSWORD_KEY, None)
        enabled = False
    safe_write_config(config, AUTH_CONFIG_FILE, backup=True)
    set_auth_config_private_permissions()
    return enabled


__all__ = [
    "AUTH_CONFIG_FILE",
    "DEFAULT_WEBUI_HOST",
    "WEBUI_ALLOWED_CLIENTS_KEY",
    "WEBUI_ALLOW_PASSWORD_CHANGE_KEY",
    "WEBUI_AUTH_SECTION",
    "WEBUI_BIND_HOST_KEY",
    "WEBUI_LEGACY_PASSWORD_KEY",
    "WEBUI_PASSWORD_KEY",
    "client_ip_allowed",
    "configured_allowed_clients",
    "configured_webui_host",
    "get_webui_password_hash",
    "hash_webui_password",
    "read_auth_config",
    "save_webui_password",
    "set_auth_config_private_permissions",
    "verify_webui_password",
    "webui_password_change_allowed",
]
