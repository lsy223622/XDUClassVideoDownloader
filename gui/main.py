#!/usr/bin/env python3
"""
Flet GUI 主入口

实现应用骨架、路由切换和日志面板集成。
"""

import flet as ft

from gui.components.log_panel import LogPanel
from gui.components.nav_rail import create_nav_rail
from gui.state import app_state
from gui.views.batch import BatchView
from gui.views.home import HomeView
from gui.views.settings import SettingsView
from utils import add_gui_log_handler, remove_gui_log_handler


def main(page: ft.Page):
    """Flet 应用主函数。"""

    # ---- 窗口配置 ----
    page.title = "XDU 课程视频下载器"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window.width = 900
    page.window.height = 680
    page.window.min_width = 700
    page.window.min_height = 500
    page.padding = 0

    # ---- 日志面板 ----
    log_panel = LogPanel()

    def _on_log(msg: str):
        """GUI 日志回调（从后台线程调用）。"""
        app_state.append_log(msg)
        log_panel.append_log(msg)
        try:
            page.update()
        except Exception:
            pass

    gui_handler = add_gui_log_handler(_on_log)

    # ---- 视图 ----
    home_view = HomeView(page)
    batch_view = BatchView(page)
    settings_view = SettingsView(page)

    views = [home_view, batch_view, settings_view]
    current_view_index = 0

    # 主内容区
    content_area = ft.Container(
        content=views[current_view_index],
        expand=True,
    )

    nav_rail = create_nav_rail(on_change=None, selected_index=current_view_index)

    def _on_nav_change(e):
        nonlocal current_view_index
        idx = e.control.selected_index
        if 0 <= idx < len(views):
            current_view_index = idx
            nav_rail.selected_index = idx
            content_area.content = views[idx]
            page.update()

    nav_rail.on_change = _on_nav_change

    # ---- 主布局 ----
    page.add(
        ft.Column(
            [
                # 上部：导航 + 内容区
                ft.Row(
                    [
                        nav_rail,
                        ft.VerticalDivider(width=1),
                        content_area,
                    ],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                # 下部：日志面板
                ft.Divider(height=1),
                log_panel,
            ],
            expand=True,
            spacing=0,
        )
    )

    # ---- 清理 ----
    def _on_close(e):
        remove_gui_log_handler(gui_handler)

    page.on_close = _on_close
