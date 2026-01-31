#!/usr/bin/env python3
"""
西安电子科技大学录直播平台课程视频下载器 - 主程序
用于下载单门课程的所有视频或指定视频

主要功能：
- 支持交互式和命令行模式下载
- 智能的视频筛选和过滤
- 断点续传和错误恢复
- 自动合并相邻节次视频
- 完整的日志记录和进度跟踪

安全特性：
- 输入验证和参数检查
- 文件完整性验证
- 异常处理和资源清理
- 用户友好的错误提示
"""

import logging
import sys
import traceback
from argparse import ArgumentParser, Namespace
from typing import Optional, Tuple

from api import check_update
from downloader import download_course_videos
from utils import enable_debug_file_logging, handle_exception, parse_week_ranges, setup_logging, user_input_with_check
from validator import make_choice_validator, validate_download_parameters, validate_live_id

# 使用统一的日志配置（模块日志 + 总日志；控制台仅 error+）
logger = setup_logging("main")

# 注意：是否启用 debug 日志，将在 __main__ 中根据命令行参数决定；
# 版本检查也延后到参数解析之后，确保若开启 debug 能记录网络日志。


def get_user_input_interactive() -> Tuple[Optional[str], Optional[str], Optional[int], Optional[bool], Optional[str]]:
    """
    交互式获取用户输入。

    返回:
        tuple: (live_id, skip_weeks_str, single, merge, video_type)
    """
    try:

        def _clear_prev_lines(n: int) -> None:
            """清除前 n 行输出"""
            for _ in range(n):
                sys.stdout.write("\033[F")  # 光标上移一行
                sys.stdout.write("\033[K")  # 清除当前行

        # 输入 LiveID
        live_id = user_input_with_check(
            "请输入 LiveID: ", validate_live_id, error_message="LiveID 格式不正确，请输入一个正数字", allow_empty=True
        )

        if not live_id:
            print("未输入 LiveID，程序退出")
            return None, None, None, None, None

        # 下载模式选择
        print("\n请选择下载模式：")
        print("1. 下载全部视频（默认）")
        print("2. 单节课模式（下载每节课的视频）")
        print("3. 半节课模式（下载每半节课的视频）")

        mode_choice = user_input_with_check(
            "请输入选择（1-3，直接回车选择默认）: ",
            make_choice_validator("1", "2", "3", allow_empty=True),
            error_message="选择无效，请输入 1、2、3 或直接回车",
            allow_empty=True,
        ).strip()

        if mode_choice == "2":
            single = 1
        elif mode_choice == "3":
            single = 2
        else:
            single = 0

        # 合并选择
        print("\n是否启用自动合并相邻节次视频？")
        print("1. 是（默认）")
        print("2. 否")

        merge_choice = user_input_with_check(
            "请输入选择（1-2，直接回车选择默认）: ",
            make_choice_validator("1", "2", allow_empty=True),
            error_message="选择无效，请输入 1、2 或直接回车",
            allow_empty=True,
        ).strip()

        merge = merge_choice != "2"

        # 视频类型选择
        print("\n请选择要下载的视频类型：")
        print("1. 两种都下载（默认）")
        print("2. 仅下载 pptVideo")
        print("3. 仅下载 teacherTrack")

        video_type_choice = user_input_with_check(
            "请输入选择（1-3，直接回车选择默认）: ",
            make_choice_validator("1", "2", "3", allow_empty=True),
            error_message="选择无效，请输入 1、2、3 或直接回车",
            allow_empty=True,
        ).strip()

        if video_type_choice == "2":
            video_type = "ppt"
        elif video_type_choice == "3":
            video_type = "teacher"
        else:
            video_type = "both"

        # 跳过周数设置
        print("\n是否需要跳过特定周数的视频？")
        print("支持以下格式（或直接回车跳过此设置）：")
        print("  - 单个周数：5")
        print("  - 范围：1-5 （跳过第1到5周）")
        print("  - 逗号分隔：1,3,5 （跳过第1、3、5周）")
        print("  - 组合：1-3,7,9-11 （跳过1-3周、第7周、9-11周）")

        def validate_skip_weeks(weeks_str: str) -> bool:
            if not weeks_str:
                return True
            try:
                parse_week_ranges(weeks_str)
                return True
            except ValueError:
                return False

        skip_weeks_input = user_input_with_check(
            "跳过的周数: ",
            validate_skip_weeks,
            error_message="格式错误，请按照示例格式输入",
            allow_empty=True
        ).strip()

        skip_weeks_str = skip_weeks_input if skip_weeks_input else ""

        # 清屏显示选择结果
        _clear_prev_lines(25)
        print("您的选择：")
        print(f"LiveID: {live_id}")
        mode_desc = {0: "全部视频", 1: "单节课模式", 2: "半节课模式"}
        print(f"下载模式: {mode_desc[single]}")
        print(f"自动合并: {'是' if merge else '否'}")
        video_type_desc = {"both": "两种都下载", "ppt": "仅 pptVideo", "teacher": "仅 teacherTrack"}
        print(f"视频类型: {video_type_desc[video_type]}")
        if skip_weeks_str:
            try:
                weeks_set = parse_week_ranges(skip_weeks_str)
                if weeks_set:
                    weeks_list = sorted(list(weeks_set))
                    if len(weeks_list) <= 10:
                        print(f"跳过周数: {', '.join(map(str, weeks_list))}")
                    else:
                        print(f"跳过周数: {', '.join(map(str, weeks_list[:10]))}... (共{len(weeks_list)}周)")
            except ValueError:
                pass
        print()

        return live_id, skip_weeks_str, single, merge, video_type

    except KeyboardInterrupt:
        print("\n用户取消操作")
        return None, None, None, None, None
    except Exception as e:
        logger.error(f"获取用户输入时发生错误: {e}")
        print(f"输入处理错误: {e}")
        return None, None, None, None, None


def parse_main_arguments() -> Namespace:
    """
    解析主程序的命令行参数。

    返回:
        argparse.Namespace: 包含所有命令行参数的对象
    """
    parser = ArgumentParser(description="西安电子科技大学录直播平台课程视频下载工具")
    parser.add_argument("liveid", nargs="?", default=None, help="课程的 LiveID（可选）")
    parser.add_argument(
        "-s",
        "--single",
        action="store_const",
        const=1,
        default=0,
        help="单节课模式：为每节课单独下载视频（而不是合并相邻节次）",
    )
    parser.add_argument(
        "-ss",
        "--single-session",
        action="store_const",
        const=2,
        dest="single",
        help="半节课模式：为每半节课单独下载视频",
    )
    parser.add_argument(
        "--no-merge", action="store_false", dest="merge", default=True, help="禁用自动合并相邻节次的视频文件"
    )
    parser.add_argument(
        "--video-type",
        choices=["both", "ppt", "teacher"],
        default="both",
        help="选择要下载的视频类型：both（两种都下载，默认）、ppt（仅下载 pptVideo）、teacher（仅下载 teacherTrack）",
    )
    parser.add_argument(
        "--skip-weeks",
        type=str,
        default="",
        metavar="WEEKS",
        help="跳过特定周数的视频。格式示例：5 (第5周), 1-5 (第1-5周), 1,3,5 (第1、3、5周), 1-3,7,9-11 (组合)",
    )
    parser.add_argument(
        "--debug", action="store_true", dest="debug", default=False, help="启用调试日志（写入 logs/debug.log）"
    )
    return parser.parse_args()


def main(liveid: Optional[str] = None, single: int = 0, merge: bool = True, video_type: str = "both", skip_weeks: str = "") -> bool:
    """
    主函数：下载指定课程的视频，包含完整的错误处理和用户体验优化。

    参数:
        liveid (Optional[str]): 课程直播 ID，为 None 时进入交互模式。
        single (int): 下载模式（0=全部，1=单节课，2=半节课）。
        merge (bool): 是否自动合并相邻节次视频。
        video_type (str): 视频类型（"both"、"ppt"、"teacher"）。
        skip_weeks (str): 跳过的周数范围字符串（如 "1-5,7,9-11"）。

    返回:
        bool: 处理是否成功
    """
    try:
        logger.info("开始执行视频下载任务")

        # 初始化认证系统
        try:
            from config import get_auth_cookies

            auth_cookies = get_auth_cookies()
            logger.info("认证系统初始化成功")
        except Exception as e:
            logger.critical(f"认证系统初始化失败: {e}")
            print(f"认证失败: {e}")
            return False

        # 交互模式：用户输入参数
        if liveid is None:
            result = get_user_input_interactive()
            if result is None or result[0] is None:
                return False
            liveid, skip_weeks, single, merge, video_type = result
        else:
            # 验证命令行参数
            liveid, single, video_type = validate_download_parameters(liveid, single, video_type)
            # skip_weeks 从参数传入

            # 无 command 参数

        # 验证并解析 skip_weeks
        skip_weeks_set = set()
        if skip_weeks:
            try:
                skip_weeks_set = parse_week_ranges(skip_weeks)
                if skip_weeks_set:
                    logger.info(f"将跳过以下周数: {sorted(list(skip_weeks_set))}")
            except ValueError as e:
                logger.error(f"跳过周数格式错误: {e}")
                print(f"错误：跳过周数格式无效 - {e}")
                return False

        logger.info(f"下载参数 - 课程 ID: {liveid}, 模式: {single}, 合并: {merge}, 类型: {video_type}")

        # 调用核心下载函数
        return download_course_videos(liveid, single, merge, video_type, skip_weeks_set)

    except KeyboardInterrupt:
        print("\n\n用户取消下载任务")
        return False
    except Exception as e:
        error_msg = handle_exception(e, "下载任务执行失败")
        print(f"\n{error_msg}")
        return False


if __name__ == "__main__":
    # 解析命令行参数
    args = parse_main_arguments()

    # 根据 --debug 参数启用调试日志文件
    if getattr(args, "debug", False):
        enable_debug_file_logging()
        logger.info("已启用调试日志输出（logs/debug.log）")

    # 现在执行版本检查（可记录网络调试日志）
    try:
        check_update()
    except Exception as e:
        logger.debug(f"检查更新时出现异常: {e}")

    try:
        # 调用主函数，传入解析后的参数
        success = main(liveid=args.liveid, single=args.single, merge=args.merge, video_type=args.video_type, skip_weeks=args.skip_weeks)

        # 根据执行结果设置退出码
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
        sys.exit(1)
