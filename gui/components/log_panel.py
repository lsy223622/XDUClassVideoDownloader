#!/usr/bin/env python3
"""可折叠日志面板组件"""

import flet as ft


class LogPanel(ft.Column):
    """底部可折叠的日志面板，实时显示应用日志。"""

    def __init__(self):
        super().__init__()
        self.auto_scroll = True
        self._max_lines = 500

        # 日志列表
        self.log_list = ft.ListView(
            expand=True,
            spacing=1,
            auto_scroll=True,
        )

        # 工具栏
        self.toolbar = ft.Row(
            [
                ft.Icon(ft.Icons.TERMINAL, size=16),
                ft.Text("日志", size=13, weight=ft.FontWeight.W_500),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.VERTICAL_ALIGN_BOTTOM,
                    icon_size=16,
                    tooltip="自动滚动",
                    on_click=self._toggle_auto_scroll,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_SWEEP,
                    icon_size=16,
                    tooltip="清空日志",
                    on_click=self._clear_logs,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            height=32,
        )

        # 日志区域容器
        self.log_container = ft.Container(
            content=self.log_list,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            border_radius=6,
            padding=8,
            height=180,
        )

        self.controls = [
            self.toolbar,
            self.log_container,
        ]
        self.spacing = 0

    def append_log(self, msg: str):
        """向日志面板追加一条消息。线程安全（需在调用后 page.update）。"""
        # 按日志级别着色
        color = None
        if "[ERROR]" in msg or "[CRITICAL]" in msg:
            color = ft.Colors.RED_400
        elif "[WARNING]" in msg:
            color = ft.Colors.ORANGE_400
        elif "[DEBUG]" in msg:
            color = ft.Colors.BLUE_GREY_400

        self.log_list.controls.append(
            ft.Text(msg, size=11, color=color, selectable=True, no_wrap=False)
        )
        # 限制行数
        if len(self.log_list.controls) > self._max_lines:
            self.log_list.controls = self.log_list.controls[-self._max_lines:]

    def _toggle_auto_scroll(self, e):
        self.log_list.auto_scroll = not self.log_list.auto_scroll
        if self.page:
            self.page.update()

    def _clear_logs(self, e):
        self.log_list.controls.clear()
        if self.page:
            self.page.update()
