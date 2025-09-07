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

import sys
import time
import traceback
import logging
from pathlib import Path
from argparse import ArgumentParser

# 本地模块导入
from api import check_update
from utils import setup_logging, handle_exception
from config import safe_read_config, AUTOMATION_CONFIG_FILE, create_initial_config, update_existing_config
from downloader import process_all_courses

# 设置日志 - 详细日志保存到文件，控制台只显示重要信息
logger = setup_logging('automation', level=logging.INFO,
                       console_level=logging.WARNING)


def parse_automation_arguments():
    """
    解析自动化程序的命令行参数。

    返回:
        argparse.Namespace: 包含所有命令行参数的对象
    """
    parser = ArgumentParser(description="西安电子科技大学录直播平台课程视频自动化批量下载工具")
    parser.add_argument('-u', '--uid', default=None,
                        help="用户的 UID（用户ID）")
    parser.add_argument('-y', '--year', type=int, default=None,
                        help="学年，例如 2023 表示 2023-2024 学年")
    parser.add_argument('-t', '--term', type=int, choices=[1, 2], default=None,
                        help="学期：1表示第一学期（秋季），2表示第二学期（春季）")
    parser.add_argument('--video-type', choices=['both', 'ppt', 'teacher'], default=None,
                        help="选择要下载的视频类型：both（两种都下载，默认）、ppt（仅下载pptVideo）、teacher（仅下载teacherTrack）")
    return parser.parse_args()


def main():
    """
    自动化下载主函数：扫描用户的所有课程并批量下载视频。

    功能流程：
    1. 解析命令行参数或读取配置文件
    2. 扫描用户的所有课程
    3. 更新配置文件（如有新课程）
    4. 批量下载所有启用下载的课程视频

    返回:
        bool: 处理是否成功
    """
    try:
        logger.info("开始执行自动化批量下载任务")

        # 检查程序更新
        try:
            check_update()
        except Exception as e:
            logger.debug(f"检查更新时出现异常: {e}")

        # 初始化认证系统
        try:
            from config import get_auth_cookies
            auth_cookies = get_auth_cookies()
            logger.info("认证系统初始化成功")
        except Exception as e:
            logger.error(f"认证系统初始化失败: {e}")
            print(f"认证失败: {e}")
            return False

        # 解析命令行参数
        args = parse_automation_arguments()

        # 计算默认学期参数
        current_time = time.localtime()
        term_year = current_time.tm_year
        month = current_time.tm_mon

        # 根据月份确定学期：9月及以后为第一学期，3月及以后为第二学期
        term_id = 1 if month >= 9 or month < 3 else 2
        if month < 9:  # 1-8月属于上一学年
            term_year -= 1

        # 处理配置文件
        if not Path(AUTOMATION_CONFIG_FILE).exists():
            # 首次运行：创建配置文件
            success = create_initial_config(
                args, term_year, term_id, AUTOMATION_CONFIG_FILE)
            if not success:
                return False
        else:
            # 已存在配置文件：读取并更新
            config = safe_read_config(AUTOMATION_CONFIG_FILE)
            success = update_existing_config(
                args, term_year, term_id, config, AUTOMATION_CONFIG_FILE)
            if not success:
                return False

        # 重新读取配置文件以获取最新配置
        try:
            config = safe_read_config(AUTOMATION_CONFIG_FILE)
        except Exception as e:
            error_msg = handle_exception(e, "读取配置文件失败")
            print(f"\n{error_msg}")
            return False

        video_type = args.video_type if args.video_type else config['DEFAULT'].get(
            'video_type', 'both')

        # 批量处理所有启用下载的课程
        return process_all_courses(config, video_type)

    except KeyboardInterrupt:
        print("\n\n用户取消自动化下载任务")
        return False
    except Exception as e:
        error_msg = handle_exception(e, "自动化下载任务执行失败")
        print(f"\n{error_msg}")
        return False


if __name__ == "__main__":
    try:
        # 调用主函数开始自动化下载
        success = main()

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
