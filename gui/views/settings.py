#!/usr/bin/env python3
"""设置视图 — 认证管理、FFmpeg 检测、下载设置"""

import threading

import flet as ft

from gui.state import app_state


class SettingsView(ft.Column):
    """设置页面：认证、FFmpeg、下载目录。"""

    def __init__(self, page: ft.Page):
        super().__init__()
        self._page = page
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO
        self.spacing = 20
        self.horizontal_alignment = ft.CrossAxisAlignment.START

        # ---- 认证方式 ----
        self.auth_method_dd = ft.Dropdown(
            label="认证方式",
            width=300,
            options=[
                ft.dropdown.Option("ids", "统一身份认证（推荐）"),
                ft.dropdown.Option("chaoxing", "超星账号密码"),
                ft.dropdown.Option("cookies", "手动输入 Cookie"),
            ],
            value=app_state.auth_method,
        )
        self.auth_method_dd.on_change = self._on_auth_method_change

        # IDS / 超星 输入
        self.username_field = ft.TextField(label="学号 / 用户名", width=300)
        self.password_field = ft.TextField(label="密码", width=300, password=True, can_reveal_password=True)

        # Cookie 输入
        self.cookie_d_field = ft.TextField(label="_d", width=300)
        self.cookie_uid_field = ft.TextField(label="UID", width=300)
        self.cookie_vc3_field = ft.TextField(label="vc3", width=300)

        self.cookie_fields = ft.Column(
            [self.cookie_d_field, self.cookie_uid_field, self.cookie_vc3_field],
            visible=app_state.auth_method == "cookies",
            spacing=8,
        )
        self.credential_fields = ft.Column(
            [self.username_field, self.password_field],
            visible=app_state.auth_method != "cookies",
            spacing=8,
        )

        self.login_btn = ft.ElevatedButton(
            "登录 / 保存", icon=ft.Icons.LOGIN, on_click=self._on_login_click
        )
        self.auth_status = ft.Text(
            "已认证" if app_state.auth_valid else "未认证",
            color=ft.Colors.GREEN_400 if app_state.auth_valid else ft.Colors.RED_400,
            size=13,
        )
        self.auth_progress = ft.ProgressRing(width=20, height=20, visible=False)

        auth_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("认证设置", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row([self.auth_method_dd, self.auth_status, self.auth_progress]),
                    self.credential_fields,
                    self.cookie_fields,
                    self.login_btn,
                ],
                spacing=12,
            ),
            padding=16,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=10,
        )

        # ---- FFmpeg ----
        ffmpeg_status = "可用" if app_state.ffmpeg_available else "不可用"
        ffmpeg_color = ft.Colors.GREEN_400 if app_state.ffmpeg_available else ft.Colors.ORANGE_400
        ffmpeg_detail = app_state.ffmpeg_path if app_state.ffmpeg_available else "未检测到 FFmpeg，合并功能不可用"

        ffmpeg_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("FFmpeg", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        ft.Text(f"状态: {ffmpeg_status}", color=ffmpeg_color, size=13),
                    ]),
                    ft.Text(ffmpeg_detail, size=12, color=ft.Colors.OUTLINE, selectable=True),
                ],
                spacing=8,
            ),
            padding=16,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=10,
        )

        # ---- 下载设置 ----
        self.video_type_dd = ft.Dropdown(
            label="默认视频类型",
            width=300,
            options=[
                ft.dropdown.Option("both", "PPT + 教师（全部）"),
                ft.dropdown.Option("ppt", "仅 PPT 视频"),
                ft.dropdown.Option("teacher", "仅教师视频"),
            ],
            value=app_state.default_video_type,
        )
        self.video_type_dd.on_change = self._on_video_type_change

        download_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("下载设置", size=18, weight=ft.FontWeight.BOLD),
                    self.video_type_dd,
                ],
                spacing=8,
            ),
            padding=16,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=10,
        )

        # 回填已保存凭证
        self._prefill_credentials()

        self.controls = [
            ft.Container(
                content=ft.Column(
                    [auth_section, ffmpeg_section, download_section],
                    spacing=16,
                ),
                padding=ft.padding.only(left=24, right=24, top=16, bottom=16),
            )
        ]

    def _prefill_credentials(self):
        """从配置文件回填已保存的凭证。"""
        creds = app_state.get_saved_credentials()
        method = creds.get("auth_method", "ids")
        self.auth_method_dd.value = method
        if method in ("ids", "chaoxing"):
            self.username_field.value = creds.get("username", "")
            self.password_field.value = creds.get("password", "")
            self.credential_fields.visible = True
            self.cookie_fields.visible = False
        else:
            self.cookie_d_field.value = creds.get("_d", "")
            self.cookie_uid_field.value = creds.get("UID", "")
            self.cookie_vc3_field.value = creds.get("vc3", "")
            self.credential_fields.visible = False
            self.cookie_fields.visible = True

    def _on_auth_method_change(self, e):
        method = self.auth_method_dd.value
        is_cookie = method == "cookies"
        self.credential_fields.visible = not is_cookie
        self.cookie_fields.visible = is_cookie
        if method == "ids":
            self.username_field.label = "学号"
        elif method == "chaoxing":
            self.username_field.label = "超星用户名"
        self._page.update()

    def _on_video_type_change(self, e):
        app_state.default_video_type = self.video_type_dd.value

    def _on_login_click(self, e):
        method = self.auth_method_dd.value
        self.login_btn.disabled = True
        self.auth_progress.visible = True
        self.auth_status.value = "认证中..."
        self.auth_status.color = ft.Colors.OUTLINE
        self._page.update()

        def _do_login():
            try:
                from config import get_auth_cookies_noninteractive
                from api import FID

                if method == "cookies":
                    creds = {
                        "_d": self.cookie_d_field.value.strip(),
                        "UID": self.cookie_uid_field.value.strip(),
                        "vc3": self.cookie_vc3_field.value.strip(),
                    }
                else:
                    creds = {
                        "username": self.username_field.value.strip(),
                        "password": self.password_field.value.strip(),
                    }

                cookies = get_auth_cookies_noninteractive(method, creds, fid=FID)
                app_state.auth_cookies = cookies
                app_state.auth_method = method
                app_state.auth_valid = True

                self.auth_status.value = "认证成功"
                self.auth_status.color = ft.Colors.GREEN_400
                self._page.snack_bar = ft.SnackBar(
                    ft.Text("认证成功！"), bgcolor=ft.Colors.GREEN_700
                )
                self._page.snack_bar.open = True

            except Exception as ex:
                app_state.auth_valid = False
                self.auth_status.value = f"失败: {ex}"
                self.auth_status.color = ft.Colors.RED_400
                self._page.snack_bar = ft.SnackBar(
                    ft.Text(f"认证失败: {ex}"), bgcolor=ft.Colors.RED_700
                )
                self._page.snack_bar.open = True

            finally:
                self.login_btn.disabled = False
                self.auth_progress.visible = False
                self._page.update()

        threading.Thread(target=_do_login, daemon=True).start()
