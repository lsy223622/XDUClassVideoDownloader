#!/usr/bin/env python3
"""
GUI 全局状态管理

管理跨视图共享的应用状态：认证、下载目录、FFmpeg 可用性等。
"""

import configparser
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

from config import (
    AUTH_CONFIG_FILE,
    REQUIRED_AUTH_COOKIES,
    has_valid_auth_cookies,
    safe_read_config,
)
from downloader import check_ffmpeg_availability, get_ffmpeg_path


class AppState:
    """应用全局状态，在各视图间共享。"""

    def __init__(self):
        # 认证状态
        self.auth_cookies: Optional[Dict[str, str]] = None
        self.auth_method: str = "ids"
        self.auth_valid: bool = False

        # 下载设置
        self.download_dir: str = os.getcwd()
        self.default_video_type: str = "both"

        # FFmpeg
        self.ffmpeg_available: bool = False
        self.ffmpeg_path: str = ""

        # 任务管理
        self.running: bool = False
        self.cancel_event: threading.Event = threading.Event()

        # 日志缓存
        self.log_messages: List[str] = []
        self._log_lock = threading.Lock()

        # 初始化检测
        self._detect_initial_state()

    def _detect_initial_state(self):
        """启动时检测已有配置和环境。"""
        # 检测 FFmpeg
        try:
            self.ffmpeg_available = check_ffmpeg_availability()
            if self.ffmpeg_available:
                self.ffmpeg_path = get_ffmpeg_path()
        except Exception:
            self.ffmpeg_available = False

        # 检测已保存的认证信息
        self._load_saved_auth()

    def _load_saved_auth(self):
        """从 auth.ini 读取已保存的认证设置。"""
        try:
            if not Path(AUTH_CONFIG_FILE).exists():
                return

            config = configparser.ConfigParser(interpolation=None)
            config.optionxform = str
            config.read(AUTH_CONFIG_FILE, encoding="utf-8")

            if "SETTINGS" in config:
                self.auth_method = config["SETTINGS"].get("auth_method", "ids")

            # 尝试判断是否有有效凭证（不做实际登录）
            if self.auth_method == "cookies" and "AUTH" in config:
                cookies = dict(config["AUTH"])
                self.auth_valid = has_valid_auth_cookies(cookies)
                if self.auth_valid:
                    self.auth_cookies = cookies
            elif self.auth_method == "ids" and "IDS_CREDENTIALS" in config:
                self.auth_valid = all(
                    config["IDS_CREDENTIALS"].get(k) for k in ("username", "password")
                )
            elif self.auth_method == "chaoxing" and "CHAOXING_CREDENTIALS" in config:
                self.auth_valid = all(
                    config["CHAOXING_CREDENTIALS"].get(k) for k in ("username", "password")
                )
        except Exception:
            self.auth_valid = False

    def get_saved_credentials(self) -> Dict[str, str]:
        """获取已保存的凭证（不含密码明文显示，仅在回填时使用）。"""
        result = {"auth_method": self.auth_method}
        try:
            if not Path(AUTH_CONFIG_FILE).exists():
                return result

            config = configparser.ConfigParser(interpolation=None)
            config.optionxform = str
            config.read(AUTH_CONFIG_FILE, encoding="utf-8")

            if self.auth_method == "ids" and "IDS_CREDENTIALS" in config:
                result["username"] = config["IDS_CREDENTIALS"].get("username", "")
                result["password"] = config["IDS_CREDENTIALS"].get("password", "")
            elif self.auth_method == "chaoxing" and "CHAOXING_CREDENTIALS" in config:
                result["username"] = config["CHAOXING_CREDENTIALS"].get("username", "")
                result["password"] = config["CHAOXING_CREDENTIALS"].get("password", "")
            elif self.auth_method == "cookies" and "AUTH" in config:
                for key in REQUIRED_AUTH_COOKIES:
                    result[key] = config["AUTH"].get(key, "")
        except Exception:
            pass
        return result

    def append_log(self, msg: str):
        """线程安全地添加日志消息。"""
        with self._log_lock:
            self.log_messages.append(msg)
            # 限制缓存大小
            if len(self.log_messages) > 5000:
                self.log_messages = self.log_messages[-3000:]

    def clear_logs(self):
        """清空日志缓存。"""
        with self._log_lock:
            self.log_messages.clear()

    def request_cancel(self):
        """请求取消当前任务。"""
        self.cancel_event.set()

    def reset_cancel(self):
        """重置取消标志。"""
        self.cancel_event.clear()


# 全局单例
app_state = AppState()
