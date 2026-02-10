#!/usr/bin/env python3
"""批量下载视图"""

import threading
import time

import flet as ft

from gui.components.task_card import TaskCard
from gui.state import app_state


class BatchView(ft.Column):
    """批量下载页面：扫描课程 → 勾选 → 批量下载。"""

    def __init__(self, page: ft.Page):
        super().__init__()
        self._page = page
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO
        self.spacing = 16
        self.horizontal_alignment = ft.CrossAxisAlignment.START

        # 默认学年/学期
        current_time = time.localtime()
        default_year = current_time.tm_year
        month = current_time.tm_mon
        default_term = 1 if month >= 9 or month < 3 else 2
        if month < 9:
            default_year -= 1

        # ---- 输入区域 ----
        self.uid_field = ft.TextField(label="用户 UID", width=200)
        self.year_field = ft.TextField(label="学年", width=120, value=str(default_year))
        self.term_dd = ft.Dropdown(
            label="学期",
            width=120,
            options=[
                ft.dropdown.Option("1", "第一学期"),
                ft.dropdown.Option("2", "第二学期"),
            ],
            value=str(default_term),
        )
        self.video_type_dd = ft.Dropdown(
            label="视频类型",
            width=180,
            options=[
                ft.dropdown.Option("both", "PPT + 教师"),
                ft.dropdown.Option("ppt", "仅 PPT"),
                ft.dropdown.Option("teacher", "仅教师"),
            ],
            value=app_state.default_video_type,
        )

        self.scan_btn = ft.ElevatedButton(
            "扫描课程", icon=ft.Icons.SEARCH, on_click=self._on_scan_click
        )
        self.scan_progress = ft.ProgressRing(width=20, height=20, visible=False)

        # ---- 课程列表 ----
        self.course_checkboxes = []
        self.course_data = {}  # {course_id: course_info}
        self.course_list = ft.Column(spacing=4)
        self.course_container = ft.Container(
            content=self.course_list,
            visible=False,
            padding=10,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
        )

        self.select_all_cb = ft.Checkbox(
            label="全选", value=True, visible=False
        )
        self.select_all_cb.on_change = self._on_select_all

        self.download_btn = ft.ElevatedButton(
            "开始批量下载",
            icon=ft.Icons.DOWNLOAD,
            on_click=self._on_download_click,
            visible=False,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.PRIMARY,
                color=ft.Colors.ON_PRIMARY,
            ),
        )

        # ---- 进度区域 ----
        self.task_card = TaskCard("批量进度")
        self.progress_section = ft.Column(
            [self.task_card],
            spacing=8,
            visible=False,
        )
        self.result_text = ft.Text("", size=13, visible=False)

        # 布局
        input_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text("批量下载", size=20, weight=ft.FontWeight.BOLD),
                    ft.Row([self.uid_field, self.year_field, self.term_dd], spacing=12),
                    ft.Row([self.video_type_dd, self.scan_btn, self.scan_progress], spacing=12),
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
                    [
                        input_section,
                        self.select_all_cb,
                        self.course_container,
                        self.download_btn,
                        self.progress_section,
                        self.result_text,
                    ],
                    spacing=12,
                ),
                padding=ft.padding.only(left=24, right=24, top=16, bottom=16),
            )
        ]

    def _on_select_all(self, e):
        val = self.select_all_cb.value
        for cb in self.course_checkboxes:
            cb.value = val
        self._page.update()

    def _on_scan_click(self, e):
        uid = self.uid_field.value.strip()
        if not uid:
            self._page.snack_bar = ft.SnackBar(
                ft.Text("请输入用户 UID"), bgcolor=ft.Colors.RED_700
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

        self.scan_btn.disabled = True
        self.scan_progress.visible = True
        self._page.update()

        def _do_scan():
            try:
                from api import scan_courses
                from config import get_auth_cookies

                get_auth_cookies()

                year = int(self.year_field.value.strip())
                term = int(self.term_dd.value)

                courses = scan_courses(uid, year, term)

                self.course_data = courses or {}
                self.course_checkboxes.clear()
                self.course_list.controls.clear()

                if not courses:
                    self._page.snack_bar = ft.SnackBar(
                        ft.Text("未找到任何课程"), bgcolor=ft.Colors.ORANGE_700
                    )
                    self._page.snack_bar.open = True
                else:
                    for cid, info in courses.items():
                        cb = ft.Checkbox(
                            label=f"{info.get('courseCode', '')} {info.get('courseName', '')}",
                            value=True,
                            data=cid,
                        )
                        self.course_checkboxes.append(cb)
                        self.course_list.controls.append(cb)

                    self.course_container.visible = True
                    self.select_all_cb.visible = True
                    self.download_btn.visible = True

                    self._page.snack_bar = ft.SnackBar(
                        ft.Text(f"找到 {len(courses)} 门课程"), bgcolor=ft.Colors.GREEN_700
                    )
                    self._page.snack_bar.open = True

            except Exception as ex:
                self._page.snack_bar = ft.SnackBar(
                    ft.Text(f"扫描失败: {ex}"), bgcolor=ft.Colors.RED_700
                )
                self._page.snack_bar.open = True
            finally:
                self.scan_btn.disabled = False
                self.scan_progress.visible = False
                try:
                    self._page.update()
                except Exception:
                    pass

        threading.Thread(target=_do_scan, daemon=True).start()

    def _on_download_click(self, e):
        # 收集选中的课程
        selected = [
            cb.data for cb in self.course_checkboxes if cb.value
        ]
        if not selected:
            self._page.snack_bar = ft.SnackBar(
                ft.Text("请至少选择一门课程"), bgcolor=ft.Colors.ORANGE_700
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

        video_type = self.video_type_dd.value
        self.download_btn.disabled = True
        self.progress_section.visible = True
        self.result_text.visible = False
        self.task_card.set_status("downloading")
        self.task_card.title_text.value = "批量下载中..."
        self._page.update()

        app_state.running = True
        app_state.reset_cancel()

        def _task_cb(completed, total, name):
            self.task_card.update_task_progress(completed, total, name)
            try:
                self._page.update()
            except Exception:
                pass

        def _do_batch():
            try:
                from config import get_auth_cookies
                from downloader import download_course_videos

                get_auth_cookies()

                total_courses = len(selected)
                success_count = 0

                for idx, cid in enumerate(selected):
                    info = self.course_data.get(cid, {})
                    live_id = info.get("id", cid)
                    course_name = f"{info.get('courseCode', '')} {info.get('courseName', '')}"

                    self.task_card.update_task_progress(idx, total_courses, course_name)
                    try:
                        self._page.update()
                    except Exception:
                        pass

                    try:
                        ok = download_course_videos(
                            live_id, single=0, merge=True, video_type=video_type,
                            task_callback=_task_cb,
                        )
                        if ok:
                            success_count += 1
                    except Exception as ex:
                        pass  # 错误已通过日志系统记录

                self.task_card.update_task_progress(total_courses, total_courses, "完成")
                self.task_card.set_status("done")
                self.result_text.value = f"批量下载完成: 成功 {success_count}/{total_courses} 门课程"
                self.result_text.color = ft.Colors.GREEN_400 if success_count == total_courses else ft.Colors.ORANGE_400

            except Exception as ex:
                self.task_card.set_status("failed")
                self.result_text.value = f"批量下载失败: {ex}"
                self.result_text.color = ft.Colors.RED_400
            finally:
                app_state.running = False
                self.download_btn.disabled = False
                self.result_text.visible = True
                try:
                    self._page.update()
                except Exception:
                    pass

        threading.Thread(target=_do_batch, daemon=True).start()
