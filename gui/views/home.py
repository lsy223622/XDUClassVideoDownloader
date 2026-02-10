#!/usr/bin/env python3
"""首页视图 — 单课下载"""

import threading

import flet as ft

from gui.components.task_card import TaskCard
from gui.state import app_state


class HomeView(ft.Column):
    """单课下载页面。"""

    def __init__(self, page: ft.Page):
        super().__init__()
        self._page = page
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO
        self.spacing = 16
        self.horizontal_alignment = ft.CrossAxisAlignment.START

        # ---- 输入区域 ----
        self.liveid_field = ft.TextField(
            label="LiveID",
            hint_text="请输入课程的 LiveID",
            width=300,
        )
        self.liveid_field.on_change = self._validate_liveid
        self.liveid_error = ft.Text("", size=11, color=ft.Colors.RED_400, visible=False)

        self.mode_radio = ft.RadioGroup(
            value="0",
            content=ft.Row([
                ft.Radio(value="0", label="全部视频"),
                ft.Radio(value="1", label="单节课"),
                ft.Radio(value="2", label="半节课"),
            ]),
        )

        self.merge_switch = ft.Switch(
            label="自动合并相邻节次",
            value=True,
            disabled=not app_state.ffmpeg_available,
        )

        self.video_type_dd = ft.Dropdown(
            label="视频类型",
            width=200,
            options=[
                ft.dropdown.Option("both", "PPT + 教师"),
                ft.dropdown.Option("ppt", "仅 PPT"),
                ft.dropdown.Option("teacher", "仅教师"),
            ],
            value=app_state.default_video_type,
        )

        self.skip_weeks_field = ft.TextField(
            label="跳过周数（可选）",
            hint_text="例如: 1-3,7,9-11",
            width=300,
        )

        self.download_btn = ft.ElevatedButton(
            "开始下载",
            icon=ft.Icons.DOWNLOAD,
            on_click=self._on_download_click,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.PRIMARY,
                color=ft.Colors.ON_PRIMARY,
            ),
        )

        # ---- 进度区域 ----
        self.file_card = TaskCard("文件进度")
        self.task_card = TaskCard("总体进度")
        self.progress_section = ft.Column(
            [self.task_card, self.file_card],
            spacing=8,
            visible=False,
        )

        self.result_text = ft.Text("", size=13, visible=False)

        # 布局
        input_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("单课下载", size=20, weight=ft.FontWeight.BOLD),
                    self.liveid_field,
                    self.liveid_error,
                    ft.Text("下载模式", size=13, weight=ft.FontWeight.W_500),
                    self.mode_radio,
                    ft.Row([self.merge_switch, self.video_type_dd], spacing=24),
                    self.skip_weeks_field,
                    ft.Row([self.download_btn]),
                ],
                spacing=10,
            ),
            padding=16,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=10,
        )

        self.controls = [
            ft.Container(
                content=ft.Column(
                    [input_section, self.progress_section, self.result_text],
                    spacing=12,
                ),
                padding=ft.padding.only(left=24, right=24, top=16, bottom=16),
            )
        ]

    def _validate_liveid(self, e):
        val = self.liveid_field.value.strip()
        if val and not val.isdigit():
            self.liveid_error.value = "LiveID 必须是数字"
            self.liveid_error.visible = True
        else:
            self.liveid_error.visible = False
        self._page.update()

    def _on_download_click(self, e):
        liveid = self.liveid_field.value.strip()
        if not liveid or not liveid.isdigit():
            self._page.snack_bar = ft.SnackBar(
                ft.Text("请输入有效的 LiveID"), bgcolor=ft.Colors.RED_700
            )
            self._page.snack_bar.open = True
            self._page.update()
            return

        if not app_state.auth_valid:
            self._page.snack_bar = ft.SnackBar(
                ft.Text("请先在设置页完成认证"), bgcolor=ft.Colors.ORANGE_700
            )
            self._page.snack_bar.open = True
            self._page.update()
            return

        if app_state.running:
            self._page.snack_bar = ft.SnackBar(
                ft.Text("已有下载任务在运行"), bgcolor=ft.Colors.ORANGE_700
            )
            self._page.snack_bar.open = True
            self._page.update()
            return

        # 准备参数
        single = int(self.mode_radio.value)
        merge = self.merge_switch.value and app_state.ffmpeg_available
        video_type = self.video_type_dd.value
        skip_weeks_str = self.skip_weeks_field.value.strip()

        # 重置 UI
        self.download_btn.disabled = True
        self.progress_section.visible = True
        self.result_text.visible = False
        self.file_card.set_status("waiting")
        self.task_card.set_status("waiting")
        self.task_card.title_text.value = "总体进度"
        self.file_card.title_text.value = "文件进度"
        self._page.update()

        app_state.running = True
        app_state.reset_cancel()

        def _progress_cb(downloaded, total, filename):
            """文件下载进度回调。"""
            self.file_card.update_progress(downloaded, total, filename)
            try:
                self._page.update()
            except Exception:
                pass

        def _task_cb(completed, total, name):
            """任务级进度回调。"""
            self.task_card.update_task_progress(completed, total, name)
            try:
                self._page.update()
            except Exception:
                pass

        def _do_download():
            try:
                from config import get_auth_cookies
                from downloader import download_course_videos
                from utils import parse_week_ranges

                # 确保认证初始化
                get_auth_cookies()

                skip_weeks_set = set()
                if skip_weeks_str:
                    skip_weeks_set = parse_week_ranges(skip_weeks_str)

                self.task_card.set_status("downloading")
                self.file_card.set_status("downloading")
                try:
                    self._page.update()
                except Exception:
                    pass

                success = download_course_videos(
                    liveid, single, merge, video_type, skip_weeks_set,
                    progress_callback=_progress_cb,
                    task_callback=_task_cb,
                )

                if success:
                    self.task_card.set_status("done")
                    self.file_card.set_status("done")
                    self.result_text.value = "下载完成！"
                    self.result_text.color = ft.Colors.GREEN_400
                else:
                    self.task_card.set_status("failed")
                    self.file_card.set_status("failed")
                    self.result_text.value = "下载失败，请查看日志"
                    self.result_text.color = ft.Colors.RED_400

            except Exception as ex:
                self.task_card.set_status("failed")
                self.file_card.set_status("failed")
                self.result_text.value = f"错误: {ex}"
                self.result_text.color = ft.Colors.RED_400

            finally:
                app_state.running = False
                self.download_btn.disabled = False
                self.result_text.visible = True
                try:
                    self._page.update()
                except Exception:
                    pass

        threading.Thread(target=_do_download, daemon=True).start()
