"""Authentication protocols, persistence and runtime cache for Core."""

import configparser
import time
import uuid
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from . import platform as platform_module
from .config import (
    AUTH_CONFIG_FILE,
    REQUIRED_AUTH_COOKIES,
    CaseSensitiveConfigParser,
    has_valid_auth_cookies as _config_has_valid_auth_cookies,
    safe_read_config,
    safe_write_config,
)
from .utils import user_input_with_check
from .validator import make_choice_validator


_runtime_auth_cache: Optional[Dict[str, str]] = None


def has_valid_auth_cookies(cookies: Optional[Mapping[str, str]]) -> bool:
    return _config_has_valid_auth_cookies(cookies)


def redact_auth_value(value: object) -> str:
    """Return a fixed redaction for secrets; never include the original value."""

    return "<redacted>" if value else "<empty>"


def set_runtime_auth_cookies(cookies: Mapping[str, str]) -> None:
    if not has_valid_auth_cookies(cookies):
        raise ValueError("认证信息不完整")
    global _runtime_auth_cache
    _runtime_auth_cache = {str(key): str(value) for key, value in cookies.items()}


def clear_runtime_auth_cache() -> None:
    global _runtime_auth_cache
    _runtime_auth_cache = None


def _read_saved_auth_cookies(filename: str = AUTH_CONFIG_FILE) -> Dict[str, str]:
    path = Path(filename)
    if not path.exists():
        return {}
    try:
        config = safe_read_config(str(path))
    except (OSError, configparser.Error):
        return {}
    if "AUTH" not in config:
        return {}
    return {key: str(config["AUTH"].get(key, "")) for key in REQUIRED_AUTH_COOKIES}


def _read_auth_settings(filename: str = AUTH_CONFIG_FILE) -> CaseSensitiveConfigParser:
    path = Path(filename)
    if not path.exists():
        return CaseSensitiveConfigParser()
    try:
        return safe_read_config(str(path))
    except (OSError, configparser.Error):
        return CaseSensitiveConfigParser()


def _save_auth_cookies(
    cookies: Mapping[str, str],
    *,
    auth_method: str = "cookies",
    filename: str = AUTH_CONFIG_FILE,
    save_auth_info: bool = True,
    username: str = "",
    password: str = "",
) -> None:
    if not has_valid_auth_cookies(cookies):
        raise ValueError("认证信息不完整")
    config = _read_auth_settings(filename)
    config["SETTINGS"] = {
        "auth_method": auth_method,
        "save_auth_info": "True" if save_auth_info else "False",
    }
    if auth_method in {"cookies", "chaoxing_qr"}:
        config["AUTH"] = {key: str(cookies[key]) for key in REQUIRED_AUTH_COOKIES}
    elif auth_method in {"ids", "chaoxing"}:
        section = "IDS_CREDENTIALS" if auth_method == "ids" else "CHAOXING_CREDENTIALS"
        config[section] = {"username": username, "password": password}
    safe_write_config(config, filename, backup=True)


def login_to_chaoxing_via_ids(username: str, password: str) -> Dict[str, str]:
    return platform_module.login_to_chaoxing_via_ids(username, password)


def login_to_chaoxing(username: str, password: str) -> Dict[str, str]:
    return platform_module.get_three_cookies_from_login(username, password)


def _migrate_saved_auth_config(config: CaseSensitiveConfigParser, filename: str = AUTH_CONFIG_FILE) -> None:
    changed = False
    if "SETTINGS" in config and config["SETTINGS"].get("auth_method") == "password":
        config["SETTINGS"]["auth_method"] = "chaoxing"
        changed = True
    if "CREDENTIALS" in config:
        if "CHAOXING_CREDENTIALS" not in config:
            config.add_section("CHAOXING_CREDENTIALS")
        for key, value in config["CREDENTIALS"].items():
            config["CHAOXING_CREDENTIALS"][key] = value
        config.remove_section("CREDENTIALS")
        changed = True
    if changed:
        safe_write_config(config, filename, backup=True)


def _non_empty(value: str) -> bool:
    return bool(value and value.strip())


def _get_cookies_via_login_interactively(
    auth_method: str, fid: Optional[str]
) -> Tuple[Dict[str, str], str, str]:
    if auth_method == "ids":
        title = "\n请输入您的西电统一身份认证账号信息："
        username_prompt = "学号: "
        login = login_to_chaoxing_via_ids
    else:
        title = "\n请输入您的超星账号信息："
        username_prompt = "用户名: "
        login = login_to_chaoxing
    print(title)
    username = user_input_with_check(username_prompt, _non_empty, error_message="用户名不能为空，请重新输入").strip()
    password = user_input_with_check("密码: ", _non_empty, error_message="密码不能为空，请重新输入").strip()
    print("正在登录并获取认证信息...")
    cookies = login(username, password)
    if not has_valid_auth_cookies(cookies):
        raise ValueError("登录成功但获取的 cookies 不完整")
    result = dict(cookies)
    result["fid"] = fid or ""
    print("登录成功，认证信息获取完成")
    return result, username, password


def _get_cookies_manually(fid: Optional[str]) -> Dict[str, str]:
    print("\n请按照提示输入认证 Cookies。")

    def valid_cookie(value: str) -> bool:
        return _non_empty(value) and not any(char in value for char in ("\n", "\r", "\t"))

    cookies = {"fid": fid or ""}
    error = "Cookie 值不能为空且不能包含换行符，请重新输入"
    for key in REQUIRED_AUTH_COOKIES:
        cookies[key] = user_input_with_check(
            f"请输入 {key} 的值: ", valid_cookie, error_message=error
        ).strip()
    print("认证信息输入完成")
    return cookies


def _get_cookies_from_qr_interactively(fid: Optional[str]) -> Dict[str, str]:
    qr_path = platform_module.get_app_path("logs", "chaoxing_qr_login.png")
    qr_session = ChaoxingQRLoginSession(fid=fid or "", qr_image_path=str(qr_path))
    qr_session.create_qr_image()
    print(f"二维码已生成: {qr_path.resolve()}")
    print("请使用学在西电 App 扫码，并在手机端确认登录。")
    try:
        webbrowser.open(qr_path.resolve().as_uri())
    except Exception:
        pass
    result = qr_session.poll()
    if result.status != "success" or not result.cookies or not has_valid_auth_cookies(result.cookies):
        raise ValueError(result.message or "扫码登录失败")
    cookies = dict(result.cookies)
    cookies["fid"] = fid or ""
    print("扫码登录成功，认证信息获取完成")
    return cookies


def _get_auth_info_interactively(
    config: CaseSensitiveConfigParser, fid: Optional[str], filename: str = AUTH_CONFIG_FILE
) -> Dict[str, str]:
    print("\n" + "=" * 60)
    print("需要进行身份验证以访问课程视频")
    print("=" * 60)
    print("\n请选择认证方式：")
    print("1. 使用统一身份认证登录（推荐，自动解决滑块验证码）")
    print("2. 使用超星账号密码登录")
    print("3. 使用学在西电 App 扫码登录")
    print("4. 手动输入 cookies")
    choice = user_input_with_check(
        "请输入选择（1、2、3或4）: ",
        make_choice_validator("1", "2", "3", "4"),
        error_message="选择无效，请输入1、2、3或4",
    ).strip()
    auth_method = {"1": "ids", "2": "chaoxing", "3": "chaoxing_qr", "4": "cookies"}[choice]
    save_choice = user_input_with_check(
        "\n是否保存认证信息？请输入 1 保存，2 不保存: ",
        make_choice_validator("1", "2"),
        error_message="选择无效，请输入1或2",
    ).strip()
    save_auth_info = save_choice == "1"

    username = password = ""
    if auth_method in {"ids", "chaoxing"}:
        cookies, username, password = _get_cookies_via_login_interactively(auth_method, fid)
    elif auth_method == "chaoxing_qr":
        cookies = _get_cookies_from_qr_interactively(fid)
    else:
        cookies = _get_cookies_manually(fid)

    if save_auth_info:
        _save_auth_cookies(
            cookies,
            auth_method=auth_method,
            filename=filename,
            save_auth_info=True,
            username=username,
            password=password,
        )
        print("认证信息已保存")
    else:
        config["SETTINGS"] = {"auth_method": auth_method, "save_auth_info": "False"}
        safe_write_config(config, filename)
    set_runtime_auth_cookies(cookies)
    return cookies


def get_auth_cookies(
    force_refresh: bool = False, fid: Optional[str] = None
) -> Dict[str, str]:
    """Resolve cookies from cache, persisted settings, configured login, or interactive setup."""

    global _runtime_auth_cache
    if not force_refresh and has_valid_auth_cookies(_runtime_auth_cache):
        cached = dict(_runtime_auth_cache)
        if fid is not None:
            cached["fid"] = fid or ""
        return cached

    config = _read_auth_settings()
    _migrate_saved_auth_config(config)
    settings = config["SETTINGS"] if "SETTINGS" in config else {}
    method = str(settings.get("auth_method", "ids")).strip().lower()
    save_auth_info = str(settings.get("save_auth_info", "True")).lower() == "true"

    if save_auth_info:
        saved = _read_saved_auth_cookies()
        if not force_refresh and has_valid_auth_cookies(saved):
            saved = dict(saved)
            if fid is not None:
                saved["fid"] = fid or ""
            set_runtime_auth_cookies(saved)
            return saved

    credentials_section = {
        "ids": "IDS_CREDENTIALS",
        "chaoxing": "CHAOXING_CREDENTIALS",
    }.get(method)
    if credentials_section and credentials_section in config:
        credentials = config[credentials_section]
        username = str(credentials.get("username", ""))
        password = str(credentials.get("password", ""))
        if username and password:
            try:
                cookies = (
                    login_to_chaoxing_via_ids(username, password)
                    if method == "ids"
                    else login_to_chaoxing(username, password)
                )
                if has_valid_auth_cookies(cookies):
                    result = dict(cookies)
                    if fid is not None:
                        result["fid"] = fid or ""
                    set_runtime_auth_cookies(result)
                    return result
            except Exception as exc:
                print(f"使用保存的认证信息登录失败: {exc}")
                print("将要求重新输入认证信息")

    return _get_auth_info_interactively(config, fid)


@dataclass
class QRLoginResult:
    status: str
    message: str = ""
    cookies: Optional[Dict[str, str]] = None


class ChaoxingQRLoginSession:
    """Own the HTTP state for a single QR login attempt."""

    def __init__(
        self,
        base_url: str = platform_module.CHAOXING_BASE_URL,
        refer: str = platform_module.CHAOXING_LOGIN_REFER,
        fid: str = "",
        timeout: int = 10,
        poll_interval: int = 2,
        expires: int = 180,
        qr_image_path: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.refer = refer
        self.fid = fid
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.expires = expires
        self.qr_image_path = Path(qr_image_path) if qr_image_path else Path(
            platform_module.get_app_path("logs", "chaoxing_qr_login.png")
        )
        self.session = platform_module._create_chaoxing_session()
        self.uuid = ""
        self.enc = ""
        self.page_refer = refer
        self._created = False

    def create_qr_image(self) -> bytes:
        login_url = self.base_url + "/login"
        response = self.session.get(
            login_url,
            params={"fid": self.fid or "", "newversion": "true", "refer": self.refer},
            timeout=self.timeout,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        self.uuid = platform_module._get_login_page_value(soup, response.text, "uuid")
        self.enc = platform_module._get_login_page_value(soup, response.text, "enc")
        page_fid = platform_module._get_login_page_value(soup, response.text, "fid")
        self.page_refer = urllib.parse.unquote(
            platform_module._get_login_page_value(soup, response.text, "refer") or self.refer
        )
        if not self.uuid or not self.enc:
            raise RuntimeError("登录页未返回扫码登录所需的 uuid/enc 字段")

        qr_response = self.session.get(
            self.base_url + "/createqr",
            params={"uuid": self.uuid, "fid": page_fid or self.fid or "-1"},
            timeout=self.timeout,
        )
        qr_response.raise_for_status()
        self.qr_image_path.parent.mkdir(parents=True, exist_ok=True)
        self.qr_image_path.write_bytes(qr_response.content)
        self._created = True
        return bytes(qr_response.content)

    def poll(self, is_cancelled: Optional[Callable[[], bool]] = None) -> QRLoginResult:
        if not self._created:
            self.create_qr_image()
        status_url = self.base_url + "/getauthstatus/v2"
        deadline = time.monotonic() + self.expires
        payload = {"enc": self.enc, "uuid": self.uuid, "doubleFactorLogin": "0"}
        headers = {"Referer": self.refer, "Origin": self.base_url}
        last_error = ""
        while time.monotonic() < deadline:
            if is_cancelled and is_cancelled():
                return QRLoginResult("cancelled", "二维码登录已取消")
            time.sleep(self.poll_interval)
            if is_cancelled and is_cancelled():
                return QRLoginResult("cancelled", "二维码登录已取消")
            try:
                response = self.session.post(
                    status_url, data=payload, headers=headers, timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = "扫码状态请求失败"
                continue
            if not isinstance(data, dict):
                last_error = "扫码状态响应格式错误"
                continue
            message = str(data.get("msg2") or data.get("mes") or data.get("msg") or "")
            if any(word in message for word in ("失效", "过期", "超时")):
                return QRLoginResult("expired", message)
            status = data.get("status")
            if status is True or str(status).lower() == "true":
                redirect_url = str(data.get("url") or data.get("refer") or "")
                if redirect_url:
                    self.session.get(urllib.parse.urljoin(self.base_url, redirect_url), timeout=self.timeout)
                if self.page_refer:
                    self.session.get(self.page_refer, timeout=self.timeout, allow_redirects=True)
                cookies = platform_module._extract_chaoxing_auth_cookies(self.session)
                if has_valid_auth_cookies(cookies):
                    set_runtime_auth_cookies(cookies)
                    return QRLoginResult("success", "二维码登录成功", dict(cookies))
                return QRLoginResult("failed", "扫码确认成功但未能获取完整的 Cookies")
        return QRLoginResult("failed", last_error or "扫码登录超时，请重新生成二维码")


__all__ = [
    "ChaoxingQRLoginSession",
    "QRLoginResult",
    "clear_runtime_auth_cache",
    "get_auth_cookies",
    "has_valid_auth_cookies",
    "login_to_chaoxing",
    "login_to_chaoxing_via_ids",
    "redact_auth_value",
    "set_runtime_auth_cookies",
]
