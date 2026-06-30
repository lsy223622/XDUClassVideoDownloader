#!/usr/bin/env python3
"""
Local Flask WebUI for XDUClassVideoDownloader.

The WebUI intentionally reuses the existing CLI-oriented downloader and config
helpers. It adds a local browser surface without changing the command-line
entry points or persisted automation choices unless the user explicitly saves
settings.
"""

import configparser
import contextlib
import hashlib
import hmac
import io
import json
import logging
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from argparse import ArgumentParser, Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from bs4 import BeautifulSoup
from flask import Flask, Response, jsonify, request, send_file, send_from_directory, session

import config as config_module
from api import (
    CHAOXING_BASE_URL,
    CHAOXING_LOGIN_REFER,
    FID,
    RELEASES_URL,
    UPDATE_CHECK_FAILED_MESSAGE,
    VERSION,
    _create_chaoxing_session,
    _extract_chaoxing_auth_cookies,
    _get_login_page_value,
    check_update,
    get_last_update_info,
    scan_courses,
)
from config import (
    AUTH_CONFIG_FILE,
    AUTOMATION_CONFIG_FILE,
    CaseSensitiveConfigParser,
    REQUIRED_AUTH_COOKIES,
    has_valid_auth_cookies,
    safe_read_config,
    safe_write_config,
)
from downloader import process_all_courses
from utils import get_app_path, parse_week_ranges, pause_before_exit_if_frozen, remove_invalid_chars, setup_logging
from validator import validate_download_parameters, validate_term_params, validate_user_id

logger = setup_logging("webui")

APP_DIR = get_app_path()
STATIC_DIR = APP_DIR / "webui" / "static"
ALLOWED_MEDIA_SUFFIXES = {".mp4", ".ts", ".srt", ".vtt"}
DEFAULT_WEBUI_HOST = "0.0.0.0"
DEFAULT_WEBUI_PORT = 5050
PORT_SCAN_LIMIT = 100
QUIET_ACCESS_LOG_PATHS = ("/api/settings/qr/", "/media/")
WEBUI_AUTH_SECTION = "WEBUI"
WEBUI_PASSWORD_KEY = "password_hash"
WEBUI_LEGACY_PASSWORD_KEY = "password"
WEBUI_ALLOW_PASSWORD_CHANGE_KEY = "allow_password_change"
WEBUI_PBKDF2_ITERATIONS = 120_000

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.secret_key = os.urandom(32)
WEBUI_UPDATE_INFO: Optional[Dict[str, Any]] = None


def _fallback_update_info() -> Dict[str, Any]:
    return {
        "ok": False,
        "allow_start": True,
        "current_version": VERSION,
        "latest_version": None,
        "min_version": None,
        "update_available": False,
        "message": UPDATE_CHECK_FAILED_MESSAGE,
        "releases_url": RELEASES_URL,
        "error": "检查更新失败",
    }


def _run_startup_update_check() -> bool:
    global WEBUI_UPDATE_INFO
    try:
        allowed = check_update()
        WEBUI_UPDATE_INFO = get_last_update_info() or _fallback_update_info()
        return allowed
    except Exception as exc:
        logger.debug(f"检查更新时出现异常: {exc}")
        WEBUI_UPDATE_INFO = _fallback_update_info()
        return True


def _parse_args() -> Namespace:
    parser = ArgumentParser(description="启动 XDUClassVideoDownloader WebUI")
    parser.add_argument("--host", default=DEFAULT_WEBUI_HOST, help=f"监听地址，默认 {DEFAULT_WEBUI_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_WEBUI_PORT, help=f"起始端口，默认 {DEFAULT_WEBUI_PORT}")
    parser.add_argument("--no-browser", action="store_true", help="启动后不要自动打开浏览器")
    return parser.parse_args()


def _is_port_available(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
        except OSError:
            return False
    return True


def _find_available_port(host: str, start_port: int) -> int:
    if not 1 <= start_port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")

    last_port = min(65535, start_port + PORT_SCAN_LIMIT)
    for port in range(start_port, last_port + 1):
        if _is_port_available(host, port):
            if port != start_port:
                logger.info(f"端口 {start_port} 已被占用，自动切换到 {port}")
            return port
    raise RuntimeError(f"端口 {start_port}-{last_port} 都不可用，请使用 --port 指定其他端口")


def _browser_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/"


def _open_browser_later(url: str) -> None:
    def _open() -> None:
        try:
            webbrowser.open(url)
        except Exception as exc:
            logger.debug(f"自动打开浏览器失败: {exc}")

    threading.Timer(1.0, _open).start()


class QuietWebUIAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in QUIET_ACCESS_LOG_PATHS)


def _configure_access_logging() -> None:
    werkzeug_logger = logging.getLogger("werkzeug")
    if not any(isinstance(item, QuietWebUIAccessFilter) for item in werkzeug_logger.filters):
        werkzeug_logger.addFilter(QuietWebUIAccessFilter())


def _app_info_payload() -> Dict[str, Any]:
    info = WEBUI_UPDATE_INFO or get_last_update_info() or _fallback_update_info()
    return {
        "version": info.get("current_version") or VERSION,
        "message": info.get("message") or UPDATE_CHECK_FAILED_MESSAGE,
        "latest_version": info.get("latest_version"),
        "min_version": info.get("min_version"),
        "update_available": bool(info.get("update_available")),
        "releases_url": info.get("releases_url") or RELEASES_URL,
        "update_check_ok": bool(info.get("ok")),
        "allow_start": bool(info.get("allow_start", True)),
    }


def _json_error(message: str, status: int = 400) -> Tuple[Response, int]:
    return jsonify({"ok": False, "error": message}), status


def _default_term() -> Tuple[int, int]:
    now = time.localtime()
    term_year = now.tm_year
    month = now.tm_mon
    term_id = 1 if month >= 9 or month < 3 else 2
    if month < 9:
        term_year -= 1
    return term_year, term_id


def _config_to_courses(config: configparser.ConfigParser) -> List[Dict[str, str]]:
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


def _read_automation_config() -> configparser.ConfigParser:
    return safe_read_config(AUTOMATION_CONFIG_FILE)


def _write_automation_config_from_scan(
    user_id: str, term_year: int, term_id: int, video_type: str
) -> configparser.ConfigParser:
    if not validate_user_id(user_id):
        raise ValueError("用户 ID 格式无效")
    if not validate_term_params(term_year, term_id):
        raise ValueError("学期参数无效")
    if video_type not in {"both", "ppt", "teacher"}:
        raise ValueError("视频类型无效")

    courses = scan_courses(user_id, term_year, term_id)
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
        section_name = str(course_id)
        config[section_name] = {
            "course_code": str(course.get("courseCode", "")),
            "course_name": remove_invalid_chars(str(course.get("courseName", ""))),
            "live_id": str(course.get("id", "")),
            "download": "yes",
        }
    safe_write_config(config, AUTOMATION_CONFIG_FILE)
    return config


def _refresh_automation_config(
    base_config: configparser.ConfigParser, user_id: str, term_year: int, term_id: int, video_type: str
) -> configparser.ConfigParser:
    if not validate_user_id(user_id):
        raise ValueError("用户 ID 格式无效")
    if not validate_term_params(term_year, term_id):
        raise ValueError("学期参数无效")
    if video_type not in {"both", "ppt", "teacher"}:
        raise ValueError("视频类型无效")

    courses = scan_courses(user_id, term_year, term_id)
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
        new_config[section_name] = {
            "course_code": str(course.get("courseCode", "")),
            "course_name": remove_invalid_chars(str(course.get("courseName", ""))),
            "live_id": str(course.get("id", "")),
            "download": old.get("download", "yes"),
        }
    safe_write_config(new_config, AUTOMATION_CONFIG_FILE)
    return new_config


class QueueWriter(io.TextIOBase):
    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit = emit

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        if not value:
            return 0
        self.emit(str(value))
        return len(value)

    def flush(self) -> None:
        return None


class QueueLogHandler(logging.Handler):
    def __init__(self, emit: Callable[[str], None]) -> None:
        # Match the CLI console behavior: INFO logs stay in log files, not stdout.
        super().__init__(logging.ERROR)
        self.emit_output = emit
        self.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.emit_output(self.format(record) + "\n")
        except Exception:
            pass


class DownloadJob:
    def __init__(self, target: Any, args: Tuple[Any, ...]) -> None:
        self.id = uuid.uuid4().hex
        self.target = target
        self.args = args
        self.history: List[str] = []
        self.condition = threading.Condition()
        self.status = "pending"
        self.success: Optional[bool] = None
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.thread = threading.Thread(target=self._run, name=f"webui-download-{self.id}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def emit_output(self, text: str) -> None:
        with self.condition:
            self.history.append(text)
            if len(self.history) > 5000:
                self.history = self.history[-5000:]
            self.condition.notify_all()

    def finish(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def _run(self) -> None:
        self.status = "running"
        self.started_at = time.time()
        writer = QueueWriter(self.emit_output)
        handler = QueueLogHandler(self.emit_output)
        root = logging.getLogger("xdu")
        root.addHandler(handler)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                self.success = bool(self.target(*self.args))
            self.status = "success" if self.success else "failed"
        except Exception as exc:
            self.success = False
            self.error = str(exc)
            self.status = "failed"
            self.emit_output(f"ERROR: {exc}\n")
            logger.exception("WebUI download job failed")
        finally:
            writer.flush()
            root.removeHandler(handler)
            self.finished_at = time.time()
            self.finish()


class DownloadJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, DownloadJob] = {}
        self._active_job_id: Optional[str] = None

    def start(self, target: Any, args: Tuple[Any, ...]) -> DownloadJob:
        with self._lock:
            if self._active_job_id:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in {"pending", "running"}:
                    raise RuntimeError("已有下载任务正在运行")
                self._active_job_id = None
            job = DownloadJob(target, args)
            self._jobs[job.id] = job
            self._active_job_id = job.id
            job.start()
            return job

    def get(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)

    def active(self) -> Optional[DownloadJob]:
        with self._lock:
            if not self._active_job_id:
                return None
            job = self._jobs.get(self._active_job_id)
            if job and job.status in {"pending", "running"}:
                return job
            return None


jobs = DownloadJobManager()


def _run_single_download(
    live_id: str, single: int, merge: bool, video_type: str, skip_weeks_text: str
) -> bool:
    from XDUClassVideoDownloader import main as download_main

    return download_main(
        liveid=live_id,
        single=single,
        merge=merge,
        video_type=video_type,
        skip_weeks=skip_weeks_text,
    )


def _run_batch_download(selected_sections: Iterable[str], video_type: str) -> bool:
    config = _read_automation_config()
    selected = {str(section) for section in selected_sections}
    runtime_config = deepcopy(config)
    for section_name in runtime_config.sections():
        runtime_config[section_name]["download"] = "yes" if section_name in selected else "no"
    return process_all_courses(runtime_config, video_type)


def _read_auth_config() -> CaseSensitiveConfigParser:
    config = CaseSensitiveConfigParser(interpolation=None)
    if Path(AUTH_CONFIG_FILE).exists():
        config.read(AUTH_CONFIG_FILE, encoding="utf-8")
    return config


def _section_has_values(config: configparser.ConfigParser, section: str, keys: Iterable[str]) -> bool:
    if section not in config:
        return False
    return all(str(config[section].get(key, "")).strip() for key in keys)


def _hash_webui_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, WEBUI_PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(WEBUI_PBKDF2_ITERATIONS, salt.hex(), digest.hex())


def _verify_webui_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if not stored.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored)
    try:
        _, iterations_text, salt_hex, digest_hex = stored.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_text),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def _get_webui_password_hash(config: Optional[configparser.ConfigParser] = None) -> str:
    config = config or _read_auth_config()
    if WEBUI_AUTH_SECTION not in config:
        return ""
    section = config[WEBUI_AUTH_SECTION]
    return str(section.get(WEBUI_PASSWORD_KEY, "") or section.get(WEBUI_LEGACY_PASSWORD_KEY, "")).strip()


def _webui_password_change_allowed(config: Optional[configparser.ConfigParser] = None) -> bool:
    config = config or _read_auth_config()
    if WEBUI_AUTH_SECTION not in config:
        return True
    return str(config[WEBUI_AUTH_SECTION].get(WEBUI_ALLOW_PASSWORD_CHANGE_KEY, "true")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _webui_password_enabled() -> bool:
    return bool(_get_webui_password_hash())


def _webui_access_unlocked() -> bool:
    return not _webui_password_enabled() or bool(session.get("webui_access_granted"))


def _save_webui_password(password: str) -> bool:
    config = _read_auth_config()
    if password:
        if not config.has_section(WEBUI_AUTH_SECTION):
            config.add_section(WEBUI_AUTH_SECTION)
        config[WEBUI_AUTH_SECTION][WEBUI_PASSWORD_KEY] = _hash_webui_password(password)
        if WEBUI_LEGACY_PASSWORD_KEY in config[WEBUI_AUTH_SECTION]:
            del config[WEBUI_AUTH_SECTION][WEBUI_LEGACY_PASSWORD_KEY]
        enabled = True
    else:
        if config.has_section(WEBUI_AUTH_SECTION):
            config.remove_section(WEBUI_AUTH_SECTION)
        enabled = False
    safe_write_config(config, AUTH_CONFIG_FILE, backup=True)
    return enabled


def _has_usable_auth(config: configparser.ConfigParser, auth_method: str) -> bool:
    if auth_method == "ids":
        return _section_has_values(config, "IDS_CREDENTIALS", ("username", "password"))
    if auth_method == "chaoxing":
        return _section_has_values(config, "CHAOXING_CREDENTIALS", ("username", "password"))
    if auth_method in {"cookies", "chaoxing_qr"}:
        cookies = {key: str(config["AUTH"].get(key, "")) for key in REQUIRED_AUTH_COOKIES} if "AUTH" in config else {}
        return has_valid_auth_cookies(cookies)
    return False


def _auth_uid(config: configparser.ConfigParser, auth_method: str) -> str:
    cached = getattr(config_module, "_runtime_auth_cache", None)
    if isinstance(cached, dict) and str(cached.get("UID", "")).strip():
        return str(cached.get("UID", "")).strip()

    if "AUTH" in config and str(config["AUTH"].get("UID", "")).strip():
        return str(config["AUTH"].get("UID", "")).strip()

    if auth_method in {"ids", "chaoxing"} and _has_usable_auth(config, auth_method):
        try:
            if auth_method == "ids":
                from api import login_to_chaoxing_via_ids

                cookies = login_to_chaoxing_via_ids(
                    str(config["IDS_CREDENTIALS"].get("username", "")),
                    str(config["IDS_CREDENTIALS"].get("password", "")),
                )
            else:
                from api import get_three_cookies_from_login

                cookies = get_three_cookies_from_login(
                    str(config["CHAOXING_CREDENTIALS"].get("username", "")),
                    str(config["CHAOXING_CREDENTIALS"].get("password", "")),
                )
            if has_valid_auth_cookies(cookies):
                cookies["fid"] = FID
                config_module._runtime_auth_cache = dict(cookies)
            return str(cookies.get("UID", "")).strip()
        except Exception as exc:
            logger.debug(f"自动获取登录 UID 失败: {exc}")
    return ""


def _auth_config_payload() -> Dict[str, Any]:
    config = _read_auth_config()
    settings = config["SETTINGS"] if "SETTINGS" in config else {}
    auth_method = settings.get("auth_method", "ids") if hasattr(settings, "get") else "ids"
    auth_ready = Path(AUTH_CONFIG_FILE).exists() and _has_usable_auth(config, auth_method)
    return {
        "exists": Path(AUTH_CONFIG_FILE).exists(),
        "auth_method": auth_method,
        "auth_ready": auth_ready,
        "uid": _auth_uid(config, auth_method),
        "save_auth_info": (
            str(settings.get("save_auth_info", "true")).lower() == "true" if hasattr(settings, "get") else True
        ),
        "ids": dict(config["IDS_CREDENTIALS"]) if "IDS_CREDENTIALS" in config else {"username": "", "password": ""},
        "chaoxing": (
            dict(config["CHAOXING_CREDENTIALS"])
            if "CHAOXING_CREDENTIALS" in config
            else {"username": "", "password": ""}
        ),
        "cookies": dict(config["AUTH"]) if "AUTH" in config else {"_d": "", "UID": "", "vc3": ""},
    }


def _replace_section(config: configparser.ConfigParser, section: str, values: Dict[str, str]) -> None:
    if config.has_section(section):
        config.remove_section(section)
    config.add_section(section)
    for key, value in values.items():
        config[section][key] = value


def _save_auth_payload(payload: Dict[str, Any]) -> None:
    auth_method = str(payload.get("auth_method", "ids"))
    if auth_method not in {"ids", "chaoxing", "chaoxing_qr", "cookies"}:
        raise ValueError("认证方式无效")
    save_auth_info = bool(payload.get("save_auth_info", True))

    config = _read_auth_config()
    config["SETTINGS"] = {"auth_method": auth_method, "save_auth_info": str(save_auth_info)}
    for section in ("AUTH", "IDS_CREDENTIALS", "CHAOXING_CREDENTIALS"):
        if config.has_section(section):
            config.remove_section(section)

    if auth_method == "ids":
        ids = payload.get("ids") or {}
        _replace_section(
            config,
            "IDS_CREDENTIALS",
            {"username": str(ids.get("username", "")), "password": str(ids.get("password", ""))},
        )
    elif auth_method == "chaoxing":
        chaoxing = payload.get("chaoxing") or {}
        _replace_section(
            config,
            "CHAOXING_CREDENTIALS",
            {"username": str(chaoxing.get("username", "")), "password": str(chaoxing.get("password", ""))},
        )
    elif auth_method in {"cookies", "chaoxing_qr"}:
        cookies = payload.get("cookies") or {}
        auth_values = {key: str(cookies.get(key, "")) for key in REQUIRED_AUTH_COOKIES}
        if not has_valid_auth_cookies(auth_values):
            raise ValueError("Cookie 信息不完整")
        _replace_section(config, "AUTH", auth_values)

    safe_write_config(config, AUTH_CONFIG_FILE, backup=True)
    config_module._runtime_auth_cache = None


class QRLoginJob:
    def __init__(self, fid: str = "") -> None:
        self.id = uuid.uuid4().hex
        self.fid = fid
        self.status = "pending"
        self.message = "正在生成二维码"
        self.error: Optional[str] = None
        self.cookies: Optional[Dict[str, str]] = None
        self.cancelled = threading.Event()
        self.image_path = get_app_path("logs", f"webui_qr_{self.id}.png")
        self.thread = threading.Thread(target=self._run, name=f"webui-qr-{self.id}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def cancel(self) -> None:
        self.cancelled.set()
        if self.status in {"pending", "waiting"}:
            self.status = "cancelled"
            self.message = "二维码登录已取消"

    def _run(self) -> None:
        try:
            session = _create_chaoxing_session()
            base_url = CHAOXING_BASE_URL.rstrip("/")
            login_url = base_url + "/login"
            login_params = {"fid": self.fid or "", "newversion": "true", "refer": CHAOXING_LOGIN_REFER}
            resp = session.get(login_url, params=login_params, timeout=10)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            qr_uuid = _get_login_page_value(soup, resp.text, "uuid")
            enc = _get_login_page_value(soup, resp.text, "enc")
            page_fid = _get_login_page_value(soup, resp.text, "fid")
            page_refer = urllib.parse.unquote(_get_login_page_value(soup, resp.text, "refer") or CHAOXING_LOGIN_REFER)
            if not qr_uuid or not enc:
                raise RuntimeError("登录页未返回扫码登录所需字段")

            qr_resp = session.get(base_url + "/createqr", params={"uuid": qr_uuid, "fid": page_fid or self.fid or "-1"}, timeout=10)
            qr_resp.raise_for_status()
            self.image_path.parent.mkdir(parents=True, exist_ok=True)
            self.image_path.write_bytes(qr_resp.content)
            self.status = "waiting"
            self.message = "请使用学在西电 App 扫码，并在手机端确认登录"

            status_url = base_url + "/getauthstatus/v2"
            headers = {"Referer": resp.url, "Origin": base_url}
            payload = {"enc": enc, "uuid": qr_uuid, "doubleFactorLogin": "0"}
            deadline = time.monotonic() + 180

            while time.monotonic() < deadline:
                if self.cancelled.is_set():
                    self.status = "cancelled"
                    self.message = "二维码登录已取消"
                    return
                time.sleep(2)
                if self.cancelled.is_set():
                    self.status = "cancelled"
                    self.message = "二维码登录已取消"
                    return
                status_resp = session.post(status_url, data=payload, headers=headers, timeout=10)
                status_resp.raise_for_status()
                status_data = status_resp.json()
                message = str(status_data.get("msg2") or status_data.get("mes") or status_data.get("msg") or "")
                if message:
                    self.message = message
                if any(word in message for word in ("失效", "过期", "超时")):
                    raise RuntimeError(message)
                status = status_data.get("status")
                if status is True or str(status).lower() == "true":
                    redirect_url = str(status_data.get("url") or status_data.get("refer") or "")
                    if redirect_url:
                        session.get(urllib.parse.urljoin(base_url, redirect_url), timeout=10)
                    if page_refer:
                        session.get(page_refer, timeout=10, allow_redirects=True)
                    cookies = _extract_chaoxing_auth_cookies(session)
                    if not has_valid_auth_cookies(cookies):
                        raise RuntimeError("扫码成功但未获取完整 Cookie")
                    cookies["fid"] = self.fid or ""
                    self.cookies = cookies
                    _save_qr_cookies(cookies)
                    self.status = "success"
                    self.message = "扫码登录成功，认证信息已保存"
                    return

            raise RuntimeError("扫码登录超时，请重新生成二维码")
        except Exception as exc:
            if self.cancelled.is_set():
                self.status = "cancelled"
                self.message = "二维码登录已取消"
                return
            self.status = "failed"
            self.error = str(exc)
            self.message = str(exc)
            logger.exception("WebUI QR login failed")


def _save_qr_cookies(cookies: Dict[str, str]) -> None:
    config = _read_auth_config()
    config["SETTINGS"] = {"auth_method": "chaoxing_qr", "save_auth_info": "True"}
    _replace_section(config, "AUTH", {key: cookies.get(key, "") for key in REQUIRED_AUTH_COOKIES})
    safe_write_config(config, AUTH_CONFIG_FILE, backup=True)
    config_module._runtime_auth_cache = dict(cookies)


qr_jobs: Dict[str, QRLoginJob] = {}


@app.before_request
def require_webui_access() -> Optional[Response]:
    if request.endpoint in {"index", "static", "webui_access_status", "webui_access_login"}:
        return None
    if not _webui_access_unlocked():
        return jsonify({"ok": False, "locked": True, "error": "请输入 WebUI 访问密码"}), 401
    return None


VIDEO_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<date>\d{1,2})日第(?P<week>[^周]+)周星期(?P<day>.+?)第(?P<jie>\d+(?:-\d+)?)节-(?P<track>pptVideo|teacherTrack)\.(?P<ext>mp4|ts)$"
)
SUBTITLE_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<date>\d{1,2})日第(?P<week>[^周]+)周星期(?P<day>.+?)第(?P<jie>\d+(?:-\d+)?)节\.(?P<ext>srt|vtt)$"
)


def _safe_relative_url(path: Path) -> str:
    return path.resolve().relative_to(APP_DIR.resolve()).as_posix()


def _course_title_from_dir(path: Path) -> str:
    return path.name


def _parse_jie_range(value: str) -> Tuple[int, int]:
    if "-" in value:
        start_text, end_text = value.split("-", 1)
        start, end = int(start_text), int(end_text)
    else:
        start = end = int(value)
    return min(start, end), max(start, end)


def _item_key(parts: Dict[str, str]) -> str:
    return "|".join([parts["year"], parts["month"], parts["date"], parts["week"], parts["day"], parts["jie"]])


def _item_title(parts: Dict[str, str]) -> str:
    return f"{parts['year']}年{parts['month']}月{parts['date']}日 第{parts['week']}周 星期{parts['day']} 第{parts['jie']}节"


def _same_lesson_day(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return all(str(left.get(key)) == str(right.get(key)) for key in ("year", "month", "date", "week", "day"))


def _subtitle_match_score(item: Dict[str, Any], subtitle: Dict[str, Any]) -> Optional[Tuple[int, int, int]]:
    if not _same_lesson_day(item, subtitle):
        return None
    item_start, item_end = int(item["jie_start"]), int(item["jie_end"])
    sub_start, sub_end = int(subtitle["jie_start"]), int(subtitle["jie_end"])
    if sub_start == item_start and sub_end == item_end:
        return 0, sub_start, sub_end
    if item_start <= sub_start and sub_end <= item_end:
        return 1, sub_start, sub_end
    if sub_start <= item_start and item_end <= sub_end:
        return 2, sub_start, sub_end
    if max(item_start, sub_start) <= min(item_end, sub_end):
        return 3, sub_start, sub_end
    return None


def _assign_subtitles(items: Sequence[Dict[str, Any]], subtitles: Sequence[Dict[str, Any]]) -> None:
    for item in items:
        candidates = []
        for subtitle in subtitles:
            score = _subtitle_match_score(item, subtitle)
            if score is not None:
                candidates.append((score, subtitle))
        if not candidates:
            continue
        best_group = min(score[0] for score, _subtitle in candidates)
        matched = [subtitle for score, subtitle in candidates if score[0] == best_group]
        matched.sort(key=lambda subtitle: (int(subtitle["jie_start"]), int(subtitle["jie_end"])))
        item["subtitle_urls"] = [subtitle["url"] for subtitle in matched]
        item["subtitle_url"] = item["subtitle_urls"][0]


def _index_local_library() -> Dict[str, Any]:
    courses: Dict[str, Dict[str, Any]] = {}
    subtitle_index: Dict[str, List[Dict[str, Any]]] = {}
    for file_path in APP_DIR.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in {".mp4", ".ts", ".srt", ".vtt"}:
            continue
        try:
            rel = _safe_relative_url(file_path)
        except ValueError:
            continue
        parent = file_path.parent
        course_key = _safe_relative_url(parent)
        course = courses.setdefault(
            course_key,
            {"id": course_key, "title": _course_title_from_dir(parent), "items": {}},
        )
        if file_path.suffix.lower() in {".srt", ".vtt"}:
            match = SUBTITLE_RE.match(file_path.name)
            if not match:
                continue
            parts = match.groupdict()
            jie_start, jie_end = _parse_jie_range(parts["jie"])
            subtitle_index.setdefault(course_key, []).append(
                {
                    **parts,
                    "jie_start": jie_start,
                    "jie_end": jie_end,
                    "url": "/media/" + rel,
                    "filename": file_path.name,
                }
            )
            continue

        match = VIDEO_RE.match(file_path.name)
        if not match:
            continue
        parts = match.groupdict()
        jie_start, jie_end = _parse_jie_range(parts["jie"])
        key = _item_key(parts)
        item = course["items"].setdefault(
            key,
            {
                "id": key,
                "title": _item_title(parts),
                "year": parts["year"],
                "month": parts["month"],
                "date": parts["date"],
                "week": parts["week"],
                "day": parts["day"],
                "jie": parts["jie"],
                "jie_start": jie_start,
                "jie_end": jie_end,
                "tracks": {},
                "subtitle_url": None,
                "subtitle_urls": [],
            },
        )
        item["tracks"][parts["track"]] = {
            "url": "/media/" + rel,
            "filename": file_path.name,
            "size": file_path.stat().st_size,
        }

    course_list = []
    for course_key, course in courses.items():
        items = list(course["items"].values())
        _assign_subtitles(items, subtitle_index.get(course_key, []))
        items.sort(key=lambda item: (int(item["month"]), int(item["date"]), int(item["jie_start"])))
        course_list.append({"id": course["id"], "title": course["title"], "items": items})
    course_list.sort(key=lambda item: item["title"])
    return {"courses": course_list}


@app.route("/")
def index() -> Response:
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/api/app/info", methods=["GET"])
def app_info() -> Response:
    return jsonify({"ok": True, **_app_info_payload()})


@app.route("/api/webui/access/status", methods=["GET"])
def webui_access_status() -> Response:
    enabled = _webui_password_enabled()
    return jsonify({"ok": True, "enabled": enabled, "unlocked": not enabled or bool(session.get("webui_access_granted"))})


@app.route("/api/webui/access/login", methods=["POST"])
def webui_access_login() -> Response:
    config = _read_auth_config()
    stored = _get_webui_password_hash(config)
    if not stored:
        session["webui_access_granted"] = True
        return jsonify({"ok": True, "unlocked": True})
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    if _verify_webui_password(password, stored):
        session["webui_access_granted"] = True
        return jsonify({"ok": True, "unlocked": True})
    return _json_error("密码错误", 401)


@app.route("/api/automation/config", methods=["GET"])
def get_automation_config() -> Response:
    term_year, term_id = _default_term()
    path = Path(AUTOMATION_CONFIG_FILE)
    if not path.exists():
        return jsonify(
            {
                "ok": True,
                "exists": False,
                "defaults": {"term_year": term_year, "term_id": term_id, "video_type": "both"},
                "courses": [],
            }
        )

    try:
        config = _read_automation_config()
        if request.args.get("refresh") == "1":
            user_id = request.args.get("uid") or config["DEFAULT"].get("user_id", "")
            refresh_year = int(request.args.get("year") or config["DEFAULT"].get("term_year", term_year))
            refresh_term = int(request.args.get("term") or config["DEFAULT"].get("term_id", term_id))
            video_type = request.args.get("video_type") or config["DEFAULT"].get("video_type", "both")
            config = _refresh_automation_config(config, user_id, refresh_year, refresh_term, video_type)
        default = config["DEFAULT"]
        return jsonify(
            {
                "ok": True,
                "exists": True,
                "defaults": {
                    "user_id": default.get("user_id", ""),
                    "term_year": default.get("term_year", str(term_year)),
                    "term_id": default.get("term_id", str(term_id)),
                    "video_type": default.get("video_type", "both"),
                },
                "courses": _config_to_courses(config),
            }
        )
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.route("/api/automation/config/init", methods=["POST"])
def init_automation_config() -> Response:
    payload = request.get_json(silent=True) or {}
    try:
        term_year, term_id = _default_term()
        config = _write_automation_config_from_scan(
            str(payload.get("uid", "")).strip(),
            int(payload.get("year") or term_year),
            int(payload.get("term") or term_id),
            str(payload.get("video_type") or "both"),
        )
        return jsonify({"ok": True, "exists": True, "courses": _config_to_courses(config)})
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/automation/config/selection", methods=["POST"])
def save_automation_selection() -> Response:
    payload = request.get_json(silent=True) or {}
    selected_sections = payload.get("selected_sections") or []
    if not isinstance(selected_sections, list):
        return _json_error("课程选择格式无效", 400)

    try:
        config = _read_automation_config()
        selected = {str(section) for section in selected_sections}
        for section_name in config.sections():
            config[section_name]["download"] = "yes" if section_name in selected else "no"
        safe_write_config(config, AUTOMATION_CONFIG_FILE, backup=True)
        return jsonify({"ok": True, "courses": _config_to_courses(config)})
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/download/start", methods=["POST"])
def start_download() -> Response:
    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode", "single"))
    try:
        if mode == "single":
            live_id = str(payload.get("live_id", "")).strip()
            single = int(payload.get("single", 0))
            video_type = str(payload.get("video_type", "both"))
            validate_download_parameters(live_id, single, video_type)
            skip_weeks = str(payload.get("skip_weeks", "")).strip()
            if skip_weeks:
                parse_week_ranges(skip_weeks)
            merge = bool(payload.get("merge", True))
            job = jobs.start(_run_single_download, (live_id, single, merge, video_type, skip_weeks))
        elif mode == "batch":
            selected_sections = payload.get("selected_sections") or []
            if not isinstance(selected_sections, list):
                raise ValueError("课程选择格式无效")
            if not selected_sections:
                raise ValueError("请至少选择一门课程")
            video_type = str(payload.get("video_type", "both"))
            if video_type not in {"both", "ppt", "teacher"}:
                raise ValueError("视频类型无效")
            job = jobs.start(_run_batch_download, (selected_sections, video_type))
        else:
            raise ValueError("下载模式无效")
        return jsonify({"ok": True, "job_id": job.id, "stream_url": f"/api/download/jobs/{job.id}/stream"})
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/download/jobs/<job_id>/stream", methods=["GET"])
def stream_download_job(job_id: str) -> Response:
    job = jobs.get(job_id)
    if not job:
        return _json_error("任务不存在", 404)

    def generate() -> Iterable[str]:
        yield "event: status\ndata: " + json.dumps({"status": job.status}, ensure_ascii=False) + "\n\n"
        index = 0
        while True:
            with job.condition:
                if index >= len(job.history) and job.status in {"pending", "running"}:
                    job.condition.wait(timeout=1)
                items = job.history[index:]
                index = len(job.history)
                done = job.status not in {"pending", "running"}

            for item in items:
                yield "data: " + json.dumps({"text": item}, ensure_ascii=False) + "\n\n"

            if done:
                yield "event: done\ndata: " + json.dumps(
                    {"status": job.status, "success": job.success, "error": job.error}, ensure_ascii=False
                ) + "\n\n"
                break

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/download/active", methods=["GET"])
def active_download_job() -> Response:
    job = jobs.active()
    if not job:
        return jsonify({"ok": True, "active": False})
    return jsonify(
        {
            "ok": True,
            "active": True,
            "job_id": job.id,
            "status": job.status,
            "stream_url": f"/api/download/jobs/{job.id}/stream",
        }
    )


@app.route("/api/library", methods=["GET"])
def library() -> Response:
    try:
        return jsonify({"ok": True, **_index_local_library()})
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.route("/media/<path:relative_path>", methods=["GET"])
def media(relative_path: str) -> Response:
    try:
        requested = (APP_DIR / relative_path).resolve()
        requested.relative_to(APP_DIR.resolve())
    except ValueError:
        return _json_error("路径无效", 403)
    if requested.suffix.lower() not in ALLOWED_MEDIA_SUFFIXES or not requested.exists():
        return _json_error("文件不存在或类型不允许", 404)
    return send_file(requested)


@app.route("/api/settings/auth", methods=["GET"])
def get_auth_settings() -> Response:
    try:
        return jsonify({"ok": True, **_auth_config_payload()})
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.route("/api/settings/auth", methods=["POST"])
def save_auth_settings() -> Response:
    payload = request.get_json(silent=True) or {}
    try:
        _save_auth_payload(payload)
        return jsonify({"ok": True})
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/settings/webui-password", methods=["GET"])
def get_webui_password_settings() -> Response:
    config = _read_auth_config()
    return jsonify(
        {
            "ok": True,
            "enabled": bool(_get_webui_password_hash(config)),
            "allow_password_change": _webui_password_change_allowed(config),
        }
    )


@app.route("/api/settings/webui-password", methods=["POST"])
def save_webui_password_settings() -> Response:
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    confirm = str(payload.get("confirm", ""))
    clear = bool(payload.get("clear", False))
    try:
        if not _webui_password_change_allowed():
            return _json_error("当前配置不允许从网页修改 WebUI 访问密码", 403)
        if clear:
            enabled = _save_webui_password("")
            session.pop("webui_access_granted", None)
            return jsonify({"ok": True, "enabled": enabled})
        if not password:
            raise ValueError("请输入 WebUI 访问密码")
        if password != confirm:
            raise ValueError("两次输入的密码不一致")
        enabled = _save_webui_password(password)
        session["webui_access_granted"] = True
        return jsonify({"ok": True, "enabled": enabled})
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/settings/qr/start", methods=["POST"])
def start_qr_login() -> Response:
    payload = request.get_json(silent=True) or {}
    fid = str(payload.get("fid") or FID)
    job = QRLoginJob(fid=fid)
    qr_jobs[job.id] = job
    job.start()
    return jsonify({"ok": True, "id": job.id, "image_url": f"/api/settings/qr/{job.id}/image"})


@app.route("/api/settings/qr/<job_id>", methods=["GET"])
def qr_status(job_id: str) -> Response:
    job = qr_jobs.get(job_id)
    if not job:
        return _json_error("二维码任务不存在", 404)
    return jsonify({"ok": True, "status": job.status, "message": job.message, "error": job.error})


@app.route("/api/settings/qr/<job_id>/cancel", methods=["POST"])
def cancel_qr_login(job_id: str) -> Response:
    job = qr_jobs.get(job_id)
    if job:
        job.cancel()
    return jsonify({"ok": True})


@app.route("/api/settings/qr/<job_id>/image", methods=["GET"])
def qr_image(job_id: str) -> Response:
    job = qr_jobs.get(job_id)
    if not job or not job.image_path.exists():
        return _json_error("二维码尚未生成", 404)
    return send_file(job.image_path, mimetype="image/png")


def main() -> None:
    args = _parse_args()
    _configure_access_logging()
    if not _run_startup_update_check():
        pause_before_exit_if_frozen()
        sys.exit(1)

    try:
        port = _find_available_port(args.host, args.port)
    except Exception as exc:
        print(f"WebUI 启动失败: {exc}")
        pause_before_exit_if_frozen()
        sys.exit(1)

    url = _browser_url(args.host, port)
    print(f"WebUI 正在启动: {url}")
    if sys.platform.startswith("win") and not args.no_browser:
        _open_browser_later(url)
    app.run(host=args.host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
