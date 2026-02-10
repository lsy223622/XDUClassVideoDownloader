#!/usr/bin/env python3
"""侧边栏导航组件"""

import flet as ft


def create_nav_rail(on_change, selected_index: int = 0) -> ft.NavigationRail:
    """
    创建侧边栏导航。

    参数:
        on_change: 选中项变化时的回调
        selected_index: 初始选中索引

    返回:
        ft.NavigationRail 实例
    """
    return ft.NavigationRail(
        selected_index=selected_index,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80,
        min_extended_width=200,
        leading=ft.Container(
            content=ft.Text("XDU\nDownloader", size=12, text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.BOLD),
            padding=ft.padding.only(top=10, bottom=5),
        ),
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.DOWNLOAD_OUTLINED,
                selected_icon=ft.Icons.DOWNLOAD,
                label="单课下载",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.LIST_ALT_OUTLINED,
                selected_icon=ft.Icons.LIST_ALT,
                label="批量下载",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS,
                label="设置",
            ),
        ],
    )
    rail.on_change = on_change
    return rail
