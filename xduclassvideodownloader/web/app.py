#!/usr/bin/env python3
"""
本地 Flask WebUI。

复用现有 CLI 的 downloader / config / api 逻辑，在不改变命令行入口与 automation_config.ini 行为的前提下，
提供浏览器界面用于登录、下载、库浏览与设置管理。
"""

import configparser
import logging
import os
import socket
import sys
import threading
import uuid
import webbrowser
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from flask import Flask, Response, jsonify, request, send_file, send_from_directory, session
from flask.typing import ResponseReturnValue

from ..core import ChaoxingQRLoginSession, check_update, set_runtime_auth_cookies
from ..core.config import AUTOMATION_CONFIG_FILE
from ..core.models import CourseDownloadOptions
from ..core.courses import default_term
from ..core.paths import get_app_path, get_bundled_app_path
from ..core.platform import (
    FID,
    RELEASES_URL,
    UPDATE_CHECK_FAILED_MESSAGE,
    VERSION,
    get_last_update_info,
)
from ..core.utils import (
    parse_week_ranges,
    pause_before_exit_if_frozen,
    setup_logging,
)
from ..core.validator import validate_download_parameters
from .access import (
    DEFAULT_WEBUI_HOST,
    WEBUI_BIND_HOST_KEY,
    client_ip_allowed as _client_ip_allowed,
    configured_webui_host as _configured_webui_host,
    get_webui_password_hash as _get_webui_password_hash,
    read_auth_config as _read_auth_config,
    save_webui_password as _save_webui_password,
    verify_webui_password as _verify_webui_password,
    webui_password_change_allowed as _webui_password_change_allowed,
)
from .auth import (
    auth_config_payload as _auth_config_payload,
    save_auth_payload as _save_auth_payload,
)
from .downloads import jobs
from .library import index_local_library
from .settings import (
    automation_config_payload as _automation_config_payload,
    read_automation_config as _read_automation_config,
    save_automation_courses as _save_automation_courses,
    scan_automation_courses as _scan_automation_courses,
)

logger = setup_logging("webui")

APP_DIR = get_app_path()
STATIC_DIR = get_bundled_app_path("web", "static")
ALLOWED_MEDIA_SUFFIXES = {".mp4", ".ts", ".srt", ".vtt"}
QR_CANCELLABLE_STATUSES = {"pending", "waiting"}
DEFAULT_WEBUI_PORT = 5050
PORT_SCAN_LIMIT = 100
QUIET_ACCESS_LOG_PATHS = ("/api/settings/qr/", "/api/download/jobs", "/media/")

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.config.from_mapping(TESTING=False)
app.secret_key = os.urandom(32)
WEBUI_UPDATE_INFO: Optional[Dict[str, Any]] = None

def _index_local_library() -> Dict[str, Any]:
    return index_local_library(APP_DIR)


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    """Return the WebUI application, optionally applying test configuration."""

    if test_config:
        app.config.update(test_config)
    return app


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
    parser.add_argument("--host", default=None, help=f"监听地址，默认读取 auth.ini 的 WEBUI.{WEBUI_BIND_HOST_KEY}，未设置则为 {DEFAULT_WEBUI_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_WEBUI_PORT, help=f"起始端口，默认 {DEFAULT_WEBUI_PORT}")
    parser.add_argument("--no-browser", action="store_true", help="启动后不要自动打开浏览器")
    args = parser.parse_args()
    if args.host is None:
        args.host = _configured_webui_host()
    return args


def _is_port_available(host: str, port: int) -> bool:
    # Use loopback for wildcard binds to avoid reserving all interfaces during probe.
    if host == "0.0.0.0":
        bind_host = "127.0.0.1"
    elif host == "::":
        bind_host = "::1"
    else:
        bind_host = host

    try:
        addrinfos = socket.getaddrinfo(bind_host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    for family, socktype, proto, _canon, sockaddr in addrinfos:
        with socket.socket(family, socktype, proto) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(sockaddr)
            except OSError:
                continue
            return True
    return False

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


def _json_error(message: str, status: int = 400) -> ResponseReturnValue:
    return jsonify({"ok": False, "error": message}), status


def _json_ok(**payload: Any) -> Response:
    return jsonify({"ok": True, **payload})


def _request_json(require_body: bool = False) -> Dict[str, Any]:
    if not request.is_json:
        raise ValueError("请求 Content-Type 必须是 application/json")
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ValueError("请求 JSON 必须是对象")
    if require_body and not data:
        raise ValueError("请求内容不能为空")
    return data


def _default_term() -> Tuple[int, int]:
    return default_term()


def _qr_image_url(job_id: str) -> str:
    return f"/api/settings/qr/{job_id}/image"


def _webui_password_enabled() -> bool:
    return bool(_get_webui_password_hash())


def _webui_access_unlocked() -> bool:
    return not _webui_password_enabled() or bool(session.get("webui_access_granted"))


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
        if self.status in QR_CANCELLABLE_STATUSES:
            self.status = "cancelled"
            self.message = "二维码登录已取消"

    def _run(self) -> None:
        try:
            qr_session = ChaoxingQRLoginSession(
                fid=self.fid,
                qr_image_path=str(self.image_path),
            )
            qr_session.create_qr_image()
            self.status = "waiting"
            self.message = "请使用学在西电 App 扫码，并在手机端确认登录"
            result = qr_session.poll(self.cancelled.is_set)
            if self.cancelled.is_set() or result.status == "cancelled":
                self.status = "cancelled"
                self.message = "二维码登录已取消"
                return
            if result.status == "success" and result.cookies:
                cookies = dict(result.cookies)
                cookies["fid"] = self.fid or ""
                self.cookies = cookies
                _save_qr_cookies(cookies)
                self.status = "success"
                self.message = "扫码登录成功，认证信息已保存"
                return
            self.status = "failed"
            self.error = result.message
            self.message = result.message
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
    _save_auth_payload(
        {
            "auth_method": "chaoxing_qr",
            "save_auth_info": True,
            "cookies": cookies,
        }
    )
    set_runtime_auth_cookies(cookies)


qr_jobs: Dict[str, QRLoginJob] = {}


@app.before_request
def require_webui_access() -> Optional[ResponseReturnValue]:
    try:
        if not _client_ip_allowed(request.remote_addr):
            return jsonify({"ok": False, "error": "当前客户端 IP 不允许访问 WebUI"}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    if request.endpoint in {"index", "static", "webui_access_status", "webui_access_login"}:
        return None
    if not _webui_access_unlocked():
        return jsonify({"ok": False, "locked": True, "error": "请输入 WebUI 访问密码"}), 401
    return None



@app.route("/")
def index() -> ResponseReturnValue:
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/api/app/info", methods=["GET"])
def app_info() -> ResponseReturnValue:
    return _json_ok(**_app_info_payload())


@app.route("/api/webui/access/status", methods=["GET"])
def webui_access_status() -> ResponseReturnValue:
    enabled = _webui_password_enabled()
    return _json_ok(enabled=enabled, unlocked=not enabled or bool(session.get("webui_access_granted")))


@app.route("/api/webui/access/login", methods=["POST"])
def webui_access_login() -> ResponseReturnValue:
    try:
        config = _read_auth_config()
        stored = _get_webui_password_hash(config)
        if not stored:
            session["webui_access_granted"] = True
            return _json_ok(unlocked=True)
        payload = _request_json(require_body=True)
        password = str(payload.get("password", ""))
        if _verify_webui_password(password, stored):
            session["webui_access_granted"] = True
            return _json_ok(unlocked=True)
        return _json_error("密码错误", 401)
    except ValueError as exc:
        return _json_error(str(exc), 400)


@app.route("/api/automation/config", methods=["GET", "POST"])
def automation_config() -> ResponseReturnValue:
    term_year, term_id = _default_term()
    try:
        if request.method == "POST":
            payload = _request_json(require_body=True)
            _save_automation_courses(
                AUTOMATION_CONFIG_FILE, str(payload.get("uid", "")).strip(),
                int(payload["year"]), int(payload["term"]), str(payload["video_type"]), payload["courses"],
            )
            return _json_ok()

        if not Path(AUTOMATION_CONFIG_FILE).exists():
            return _json_ok(defaults={"term_year": term_year, "term_id": term_id, "video_type": "both"},
                            courses=[])
        return _json_ok(**_automation_config_payload(_read_automation_config(AUTOMATION_CONFIG_FILE), term_year, term_id))
    except (ValueError, KeyError, TypeError, OSError, configparser.Error) as exc:
        return _json_error(str(exc), 400)


@app.route("/api/download/courses", methods=["POST"])
def scan_download_courses() -> ResponseReturnValue:
    try:
        payload = _request_json(require_body=True)
        courses = _scan_automation_courses(
            str(payload.get("uid", "")).strip(), int(payload["year"]), int(payload["term"]),
            str(payload.get("video_type", "both")),
        )
        return _json_ok(courses=courses)
    except (ValueError, KeyError, TypeError) as exc:
        return _json_error(str(exc), 400)
    except Exception:
        logger.exception("WebUI course scan failed")
        return _json_error("扫描失败，请检查网络连接和登录状态", 502)


def _course_options(payload: Dict[str, Any]) -> CourseDownloadOptions:
    live_id = str(payload.get("live_id", "")).strip()
    single = int(payload.get("single", 0))
    video_type = str(payload.get("video_type", "both"))
    validate_download_parameters(live_id, single, video_type)
    skip_weeks = str(payload.get("skip_weeks", "")).strip()
    parse_week_ranges(skip_weeks)
    return CourseDownloadOptions(live_id, single, bool(payload.get("merge", True)), video_type, skip_weeks)


@app.route("/api/download/start", methods=["POST"])
def start_download() -> ResponseReturnValue:
    try:
        payload = _request_json(require_body=True)
        mode = payload.get("mode", "single")
        if mode == "single":
            requests = [(_course_options(payload), "")]
        elif mode == "batch":
            courses = payload.get("courses")
            if not isinstance(courses, list) or not courses:
                raise ValueError("请至少选择一门课程")
            requests = [
                (_course_options({"live_id": course["live_id"], "video_type": payload.get("video_type", "both")}),
                 str(course.get("course_name", "")))
                for course in courses if isinstance(course, dict)
            ]
            if len(requests) != len(courses):
                raise ValueError("课程数据无效")
        else:
            raise ValueError("下载模式无效")
        job_ids = jobs.enqueue(requests)
        return _json_ok(job_id=job_ids[0], job_ids=job_ids)
    except (ValueError, TypeError, KeyError) as exc:
        return _json_error(str(exc), 400)


@app.route("/api/download/jobs", methods=["GET", "DELETE"])
def download_jobs() -> ResponseReturnValue:
    if request.method == "DELETE":
        jobs.clear_completed()
    paused, snapshots = jobs.queue_state()
    return _json_ok(jobs=snapshots, paused=paused)


@app.route("/api/download/jobs/<job_id>/retry", methods=["POST"])
def retry_download(job_id: str) -> ResponseReturnValue:
    job = jobs.get(job_id)
    if job is None:
        return _json_error("任务不存在", 404)
    if job.status not in {"failed", "stopped"}:
        return _json_error("只能重试失败或已停止的任务", 400)
    return _json_ok(job_id=jobs.enqueue([(job.options, job.name)])[0])



@app.route("/api/download/jobs/control", methods=["POST"])
def control_download() -> ResponseReturnValue:
    try:
        payload = _request_json(require_body=True)
        jobs.control(payload.get("action"))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    return _json_ok()


@app.route("/api/library", methods=["GET"])
def library() -> ResponseReturnValue:
    try:
        return _json_ok(**_index_local_library())
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.route("/media/<path:relative_path>", methods=["GET"])
def media(relative_path: str) -> ResponseReturnValue:
    try:
        requested = (APP_DIR / relative_path).resolve()
        requested.relative_to(APP_DIR.resolve())
    except ValueError:
        return _json_error("路径无效", 403)
    if requested.suffix.lower() not in ALLOWED_MEDIA_SUFFIXES or not requested.exists():
        return _json_error("文件不存在或类型不允许", 404)
    return send_file(requested)


@app.route("/api/settings/auth", methods=["GET"])
def get_auth_settings() -> ResponseReturnValue:
    try:
        return _json_ok(**_auth_config_payload())
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.route("/api/settings/auth", methods=["POST"])
def save_auth_settings() -> ResponseReturnValue:
    try:
        payload = _request_json(require_body=True)
        _save_auth_payload(payload)
        return _json_ok()
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/settings/webui-password", methods=["GET"])
def get_webui_password_settings() -> ResponseReturnValue:
    config = _read_auth_config()
    return _json_ok(
        enabled=bool(_get_webui_password_hash(config)),
        allow_password_change=_webui_password_change_allowed(config),
    )


@app.route("/api/settings/webui-password", methods=["POST"])
def save_webui_password_settings() -> ResponseReturnValue:
    try:
        payload = _request_json(require_body=True)
        password = str(payload.get("password", ""))
        confirm = str(payload.get("confirm", ""))
        clear = bool(payload.get("clear", False))
        if not _webui_password_change_allowed():
            return _json_error("当前配置不允许从网页修改 WebUI 访问密码", 403)
        if clear:
            enabled = _save_webui_password("")
            session.pop("webui_access_granted", None)
            return _json_ok(enabled=enabled)
        if not password:
            raise ValueError("请输入 WebUI 访问密码")
        if password != confirm:
            raise ValueError("两次输入的密码不一致")
        enabled = _save_webui_password(password)
        session["webui_access_granted"] = True
        return _json_ok(enabled=enabled)
    except Exception as exc:
        return _json_error(str(exc), 400)


@app.route("/api/settings/qr/start", methods=["POST"])
def start_qr_login() -> ResponseReturnValue:
    try:
        payload = _request_json()
        fid = str(payload.get("fid") or FID)
        job = QRLoginJob(fid=fid)
        qr_jobs[job.id] = job
        job.start()
        return _json_ok(id=job.id, image_url=_qr_image_url(job.id))
    except ValueError as exc:
        return _json_error(str(exc), 400)


@app.route("/api/settings/qr/<job_id>", methods=["GET"])
def qr_status(job_id: str) -> ResponseReturnValue:
    job = qr_jobs.get(job_id)
    if not job:
        return _json_error("二维码任务不存在", 404)
    return _json_ok(status=job.status, message=job.message, error=job.error)


@app.route("/api/settings/qr/<job_id>/cancel", methods=["POST"])
def cancel_qr_login(job_id: str) -> ResponseReturnValue:
    job = qr_jobs.get(job_id)
    if job:
        job.cancel()
    return _json_ok()


@app.route("/api/settings/qr/<job_id>/image", methods=["GET"])
def qr_image(job_id: str) -> ResponseReturnValue:
    job = qr_jobs.get(job_id)
    if not job or not job.image_path.exists():
        return _json_error("二维码尚未生成", 404)
    return send_file(job.image_path, mimetype="image/png")


def run(host: Optional[str] = None, port: int = DEFAULT_WEBUI_PORT, open_browser: bool = True) -> None:
    """Start the WebUI server with the legacy port-selection behavior."""

    host = host or _configured_webui_host()
    _configure_access_logging()
    if not _run_startup_update_check():
        pause_before_exit_if_frozen()
        sys.exit(1)

    try:
        port = _find_available_port(host, port)
    except Exception as exc:
        print(f"WebUI 启动失败: {exc}")
        pause_before_exit_if_frozen()
        sys.exit(1)

    url = _browser_url(host, port)
    print(f"WebUI 正在启动: {url}")
    if sys.platform.startswith("win") and open_browser:
        _open_browser_later(url)
    app.run(host=host, port=port, debug=False, threaded=True)


def main() -> None:
    """Compatibility entry point for the original WebUI script."""

    args = _parse_args()
    run(args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
