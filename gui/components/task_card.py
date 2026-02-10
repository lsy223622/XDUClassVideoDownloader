#!/usr/bin/env python3
"""下载任务卡片组件"""

import flet as ft
from utils import format_file_size


class TaskCard(ft.Card):
    """展示单个下载任务的进度和状态。"""

    def __init__(self, title: str = ""):
        super().__init__()
        self.title_text = ft.Text(title, size=13, weight=ft.FontWeight.W_500,
                                  overflow=ft.TextOverflow.ELLIPSIS, max_lines=1)
        self.status_text = ft.Text("等待中", size=11, color=ft.Colors.OUTLINE)
        self.progress_bar = ft.ProgressBar(value=0, width=300)
        self.detail_text = ft.Text("", size=11, color=ft.Colors.OUTLINE)

        self.content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [self.title_text, ft.Container(expand=True), self.status_text],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.progress_bar,
                    self.detail_text,
                ],
                spacing=4,
            ),
            padding=12,
        )

    def update_progress(self, downloaded: int, total: int, filename: str = ""):
        """更新下载进度。"""
        if filename:
            self.title_text.value = filename
        if total > 0:
            ratio = downloaded / total
            self.progress_bar.value = ratio
            self.detail_text.value = f"{format_file_size(downloaded)} / {format_file_size(total)} ({ratio:.0%})"
        else:
            self.progress_bar.value = None  # 不确定进度
            self.detail_text.value = f"{format_file_size(downloaded)}"
        self.status_text.value = "下载中"
        self.status_text.color = ft.Colors.BLUE_400

    def set_status(self, status: str):
        """设置任务状态。"""
        status_map = {
            "waiting": ("等待中", ft.Colors.OUTLINE),
            "downloading": ("下载中", ft.Colors.BLUE_400),
            "merging": ("合并中", ft.Colors.AMBER_400),
            "done": ("完成", ft.Colors.GREEN_400),
            "failed": ("失败", ft.Colors.RED_400),
        }
        label, color = status_map.get(status, ("未知", ft.Colors.OUTLINE))
        self.status_text.value = label
        self.status_text.color = color
        if status == "done":
            self.progress_bar.value = 1.0

    def update_task_progress(self, completed: int, total: int, name: str = ""):
        """更新任务级进度（视频数量）。"""
        if total > 0:
            self.progress_bar.value = completed / total
            self.detail_text.value = f"已完成 {completed}/{total}"
        if name:
            self.title_text.value = name
        self.status_text.value = "处理中"
        self.status_text.color = ft.Colors.BLUE_400
