#!/usr/bin/env python3
"""
西安电子科技大学录直播平台课程视频下载器 - 自动化批量下载程序

功能说明：
- 自动扫描用户的所有课程
- 智能更新课程配置文件
- 批量下载所有启用的课程视频
- 支持断点续传和错误恢复
- 多线程并行下载提升效率

安全特性：
- 完整的输入验证和参数检查
- 文件完整性验证和原子操作
- 异常处理和资源清理
- 用户友好的错误提示和进度反馈
"""

import logging
import sys
import time
import traceback
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

# 本地模块导入
from ..core import check_update, download_courses, get_auth_cookies
from ..core.config import (
    AUTOMATION_CONFIG_FILE,
    create_initial_config,
    safe_read_config,
    update_existing_config,
)
from ..core.courses import default_term
from ..core.services import scan_term_courses
from ..core.utils import (
    enable_debug_file_logging,
    handle_exception,
    pause_before_exit_if_frozen,
    setup_logging,
)

# 设置日志（模块日志 + 总日志；控制台仅 error+）
logger = setup_logging("automation")


def parse_automation_arguments() -> Namespace:
    """
    解析自动化程序的命令行参数。

    返回:
        argparse.Namespace: 包含所有命令行参数的对象
    """
    parser = ArgumentParser(description="西安电子科技大学录直播平台课程视频自动化批量下载工具")
    parser.add_argument("-u", "--uid", default=None, help="用户的 UID（用户 ID）")
    parser.add_argument("-y", "--year", type=int, default=None, help="学年，例如 2023 表示 2023-2024 学年")
    parser.add_argument(
        "-t",
        "--term",
        type=int,
        choices=[1, 2],
        default=None,
        help="学期：1 表示第一学期（秋季），2 表示第二学期（春季）",
    )
    parser.add_argument(
        "--video-type",
        choices=["both", "ppt", "teacher"],
        default=None,
        help="选择要下载的视频类型：both（两种都下载，默认）、ppt（仅下载 pptVideo）、teacher（仅下载 teacherTrack）",
    )
    parser.add_argument(
        "--debug", action="store_true", dest="debug", default=False, help="启用调试日志（写入 logs/debug.log）"
    )
    return parser.parse_args()


def main(args: Optional[Namespace] = None, config_file: Optional[str] = None) -> bool:
    """Scan, persist and download courses through the public Core facade."""

    try:
        logger.info("开始执行自动化批量下载任务")
        args = args or parse_automation_arguments()

        # 根据 --debug 参数启用调试日志文件（尽早，使后续网络请求有调试日志）
        if getattr(args, "debug", False):
            enable_debug_file_logging()
            logger.info("已启用调试日志输出（logs/debug.log）")

        # 检查程序更新
        try:
            if not check_update():
                pause_before_exit_if_frozen()
                return False
        except Exception as e:
            logger.debug(f"检查更新时出现异常: {e}")

        try:
            auth_cookies = get_auth_cookies()
            logger.info("认证系统初始化成功")
        except Exception as e:
            logger.critical(f"认证系统初始化失败: {e}")
            print(f"认证失败: {e}")
            return False

        default_year, default_term_id = default_term()
        target_file = str(config_file or AUTOMATION_CONFIG_FILE)
        target_path = Path(target_file)

        if target_path.exists():
            config = safe_read_config(target_file)
            user_id = args.uid or config["DEFAULT"].get("user_id", "")
        else:
            user_id = args.uid or input("请输入用户ID：").strip()

        term_year = args.year or default_year
        term_id = args.term or default_term_id
        courses = scan_term_courses(user_id, term_year, term_id, auth_cookies=auth_cookies)

        if not target_path.exists():
            scan_args = Namespace(
                uid=user_id,
                year=args.year,
                term=args.term,
                video_type=args.video_type,
            )
            success = create_initial_config(
                scan_args,
                default_year,
                default_term_id,
                target_file,
                courses=courses,
            )
            if not success:
                return False
        else:
            success = update_existing_config(
                args,
                default_year,
                default_term_id,
                config,
                target_file,
                courses=courses,
            )
            if not success:
                return False

        try:
            config = safe_read_config(target_file)
        except Exception as e:
            error_msg = handle_exception(e, "读取配置文件失败")
            print(f"\n{error_msg}")
            return False

        video_type = args.video_type if args.video_type else config["DEFAULT"].get("video_type", "both")

        return download_courses(
            config,
            selected_sections=None,
            video_type=video_type,
            auth_cookies=auth_cookies,
        )

    except KeyboardInterrupt:
        print("\n\n用户取消自动化下载任务")
        return False
    except Exception as e:
        error_msg = handle_exception(e, "自动化下载任务执行失败")
        print(f"\n{error_msg}")
        return False


def run() -> None:
    """Run the automation frontend and translate its result to an exit code."""

    try:
        success = main()
        pause_before_exit_if_frozen()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        sys.exit(130)  # SIGINT 退出码
    except Exception as e:
        # 捕获并显示所有未处理的异常
        logger.error(f"程序执行时发生未处理的异常: {e}")
        print(f"发生错误：{e}")
        if logger.getEffectiveLevel() <= logging.DEBUG:
            print(traceback.format_exc())
        pause_before_exit_if_frozen()
        sys.exit(1)


if __name__ == "__main__":
    run()
