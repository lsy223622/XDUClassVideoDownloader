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
import configparser
from pathlib import Path
from tqdm import tqdm
from argparse import ArgumentParser

# 本地模块导入
from api import (
    get_initial_data, get_video_info_from_html, 
    scan_courses, check_update
)
from downloader import process_rows
from utils import (
    create_directory, setup_logging, handle_exception, 
    day_to_chinese, remove_invalid_chars,
    safe_write_config, safe_read_config, validate_user_id,
    validate_term_params
)

# 设置日志 - 详细日志保存到文件，控制台只显示重要信息
logger = setup_logging('automation', level=logging.INFO, console_level=logging.WARNING)

# 配置文件名
CONFIG_FILE = 'automation_config.ini'


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

        # 解析命令行参数
        args = parse_arguments()
        
        # 计算默认学期参数
        current_time = time.localtime()
        term_year = current_time.tm_year
        month = current_time.tm_mon

        # 根据月份确定学期：9月及以后为第一学期，3月及以后为第二学期
        term_id = 1 if month >= 9 or month < 3 else 2
        if month < 9:  # 1-8月属于上一学年
            term_year -= 1

        # 处理配置文件
        if not Path(CONFIG_FILE).exists():
            # 首次运行：创建配置文件
            success = create_initial_config(args, term_year, term_id)
            if not success:
                return False
        else:
            # 已存在配置文件：读取并更新
            success = update_existing_config(args, term_year, term_id)
            if not success:
                return False

        # 重新读取配置文件以获取最新配置
        try:
            config = safe_read_config(CONFIG_FILE)
        except Exception as e:
            error_msg = handle_exception(e, "读取配置文件失败")
            print(f"\n{error_msg}")
            return False

        video_type = args.video_type if args.video_type else config['DEFAULT'].get('video_type', 'both')

        # 批量处理所有启用下载的课程
        return process_all_courses(config, video_type)

    except KeyboardInterrupt:
        print("\n\n用户取消自动化下载任务")
        return False
    except Exception as e:
        error_msg = handle_exception(e, "自动化下载任务执行失败")
        print(f"\n{error_msg}")
        return False


def create_initial_config(args, default_year, default_term):
    """
    创建初始配置文件。

    参数:
        args: 命令行参数
        default_year: 默认学年
        default_term: 默认学期

    返回:
        bool: 是否成功创建
    """
    try:
        # 获取用户输入或使用命令行参数
        if args.uid:
            user_id = args.uid
        else:
            user_id = input("请输入用户ID：").strip()
            
        if not validate_user_id(user_id):
            print("用户ID格式无效")
            return False

        term_year = args.year if args.year else default_year
        term_id = args.term if args.term else default_term
        video_type = args.video_type if args.video_type else 'both'

        # 验证学期参数
        if not validate_term_params(term_year, term_id):
            print("学期参数无效")
            return False

        # 扫描课程
        print("正在扫描课程...", end='', flush=True)
        try:
            courses = scan_courses(user_id, term_year, term_id)
            if not courses:
                print("\r" + " " * 50 + "\r没有找到任何课程，请检查用户ID和学期参数")
                return False
        except Exception as e:
            print("\r" + " " * 50 + "\r")
            error_msg = handle_exception(e, "扫描课程失败")
            print(f"{error_msg}")
            return False
        finally:
            print("\r" + " " * 50 + "\r", end='')

        # 创建配置文件
        try:
            config = configparser.ConfigParser()
            config['DEFAULT'] = {
                'user_id': user_id,
                'term_year': str(term_year),
                'term_id': str(term_id),
                'video_type': video_type
            }

            # 添加课程配置
            for course_id, course in courses.items():
                course_id_str = str(course_id)
                config[course_id_str] = {
                    'course_code': course['courseCode'],
                    'course_name': remove_invalid_chars(course['courseName']),
                    'live_id': str(course['id']),
                    'download': 'yes'
                }

            safe_write_config(config, CONFIG_FILE)
            print(f"配置文件已生成，包含 {len(courses)} 门课程")
            print("请修改配置文件后按回车继续...")
            input()
            return True

        except Exception as e:
            error_msg = handle_exception(e, "创建配置文件失败")
            print(f"{error_msg}")
            return False

    except Exception as e:
        error_msg = handle_exception(e, "初始化配置失败")
        print(f"{error_msg}")
        return False


def update_existing_config(args, default_year, default_term):
    """
    更新现有配置文件。

    参数:
        args: 命令行参数
        default_year: 默认学年
        default_term: 默认学期

    返回:
        bool: 是否成功更新
    """
    try:
        # 读取现有配置
        config = safe_read_config(CONFIG_FILE)
        
        user_id = args.uid if args.uid else config['DEFAULT']['user_id']
        term_year = args.year if args.year else int(config['DEFAULT'].get('term_year', default_year))
        term_id = args.term if args.term else int(config['DEFAULT'].get('term_id', default_term))

        # 处理旧配置文件兼容性
        video_type = args.video_type if args.video_type else config['DEFAULT'].get('video_type', 'both')

        # 验证参数
        if not validate_user_id(user_id) or not validate_term_params(term_year, term_id):
            print("配置文件中的参数无效")
            return False

        print(f"使用用户ID：{user_id}")
        logger.info(f"使用配置文件中的用户ID：{user_id}")

        # 重新扫描课程
        print("正在扫描课程...", end='', flush=True)
        try:
            new_courses = scan_courses(user_id, term_year, term_id)
        except Exception as e:
            print("\r" + " " * 50 + "\r")
            error_msg = handle_exception(e, "扫描课程失败")
            print(f"{error_msg}")
            return False
        finally:
            print("\r" + " " * 50 + "\r", end='')

        # 更新配置
        config_updated = update_course_config(config, new_courses)

        # 更新默认配置
        config['DEFAULT']['video_type'] = video_type
        config['DEFAULT']['term_year'] = str(term_year)
        config['DEFAULT']['term_id'] = str(term_id)

        # 保存更新后的配置
        try:
            safe_write_config(config, CONFIG_FILE)
        except Exception as e:
            error_msg = handle_exception(e, "保存配置文件失败")
            print(f"{error_msg}")
            return False

        # 如果有新课程，提示用户检查配置
        if config_updated:
            print("配置文件已更新，请修改配置文件后按回车继续...")
            input()

        return True

    except Exception as e:
        error_msg = handle_exception(e, "更新配置失败")
        print(f"{error_msg}")
        return False


def update_course_config(config, new_courses):
    """
    更新课程配置。

    参数:
        config: 配置对象
        new_courses: 新课程数据

    返回:
        bool: 是否有更新
    """
    config_updated = False
    existing_courses = {
        section: dict(config[section]) 
        for section in config.sections() 
        if section != 'DEFAULT'
    }

    # 处理新发现的课程
    for course_id, course in new_courses.items():
        course_id_str = str(course_id)
        
        if course_id_str not in config.sections():
            # 添加新课程
            logger.info(f"添加新课程：{course_id_str} - {course['courseName']}")
            print(f"发现新课程：{course['courseName']}")
            config[course_id_str] = {
                'course_code': course['courseCode'],
                'course_name': remove_invalid_chars(course['courseName']),
                'live_id': str(course['id']),
                'download': 'yes'
            }
            config_updated = True
        else:
            # 检查现有课程是否需要更新
            existing_course = existing_courses[course_id_str]
            if (existing_course.get('course_code') != course['courseCode'] or
                existing_course.get('course_name') != remove_invalid_chars(course['courseName']) or
                existing_course.get('live_id') != str(course['id'])):
                
                logger.info(f"更新课程信息：{course_id_str} - {course['courseName']}")
                print(f"更新课程：{course['courseName']}")
                config[course_id_str] = {
                    'course_code': course['courseCode'],
                    'course_name': remove_invalid_chars(course['courseName']),
                    'live_id': str(course['id']),
                    'download': existing_course.get('download', 'yes')
                }
                config_updated = True

    return config_updated


def process_all_courses(config, video_type):
    """
    批量处理所有启用下载的课程。

    参数:
        config: 配置对象
        video_type: 视频类型

    返回:
        bool: 处理是否成功
    """
    try:
        all_videos = {}
        # 只统计配置中设置为 download = yes 的课程数
        enabled_sections = [s for s in config.sections() if s != 'DEFAULT' and config[s].get('download') == 'yes']
        total_enabled = len(enabled_sections)
        processed_courses = 0

        print(f"\n开始处理选择下载的 {total_enabled} 门课程...")

        for course_id in config.sections():
            # 跳过DEFAULT段和未启用下载的课程
            if course_id == 'DEFAULT' or config[course_id].get('download') != 'yes':
                continue

            processed_courses += 1
            # 获取课程信息
            course_code = config[course_id]['course_code']
            course_name = remove_invalid_chars(config[course_id]['course_name'])
            live_id = config[course_id]['live_id']
            
            print(f"\n[{processed_courses}/{total_enabled}] 处理课程：{course_name}")
            logger.info(f"正在检查课程：{course_code} - {course_name} (ID: {live_id})")

            try:
                # 获取课程数据
                data = get_initial_data(int(live_id))
                if not data:
                    logger.warning(f"没有找到课程数据：{course_code}")
                    print(f"跳过课程 {course_code}")
                    continue

                # 提取课程年份并创建保存目录
                year = time.gmtime(data[0]["startTime"]["time"] / 1000).tm_year
                save_dir = f"{year}年{course_code}{course_name}"
                create_directory(save_dir)

                # 获取需要下载的视频
                rows = get_course_videos(data, course_code, course_name, year, save_dir, video_type)

                if rows:
                    all_videos[course_code] = {
                        "course_name": course_name,
                        "year": year,
                        "rows": rows,
                        "save_dir": save_dir
                    }
                    print(f"找到 {len(rows)} 个待下载视频")
                    logger.info(f"课程 {course_code} 有 {len(rows)} 个视频待下载")
                else:
                    logger.info(f"课程 {course_code} 没有新增视频")
                    print(f"课程 {course_code} 无新视频")

            except Exception as e:
                error_msg = handle_exception(e, f"处理课程 {course_code} 时发生错误")
                print(f"{error_msg}")
                continue

        # 批量下载所有课程的视频
        if all_videos:
            print(f"\n开始下载 {len(all_videos)} 门课程的视频...")
            download_success = True
            
            for course_code, course_info in all_videos.items():
                try:
                    print(f"\n正在下载课程：{course_code} - {course_info['course_name']}")
                    
                    # 使用统一的处理函数下载视频
                    stats = process_rows(
                        course_info["rows"], 
                        course_code, 
                        course_info["course_name"], 
                        course_info["year"], 
                        course_info["save_dir"],
                        command='', 
                        merge=True, 
                        video_type=video_type
                    )
                    
                    print(f"课程 {course_code} 下载完成 - 成功:{stats.get('downloaded', 0)} 失败:{stats.get('failed', 0)}")
                    
                    if stats.get('failed', 0) > 0:
                        download_success = False
                        
                except Exception as e:
                    error_msg = handle_exception(e, f"下载课程 {course_code} 时发生错误")
                    print(f"{error_msg}")
                    download_success = False

            print(f"\n所有课程视频下载{'成功' if download_success else '完成（部分失败）'}")
            return download_success
        else:
            print("\n没有发现需要下载的新视频")
            return True

    except Exception as e:
        error_msg = handle_exception(e, "批量处理课程失败")
        print(f"\n{error_msg}")
        return False


def get_course_videos(data, course_code, course_name, year, save_dir, video_type):
    """
    获取课程的待下载视频列表。

    参数:
        data: 课程数据
        course_code: 课程代码
        course_name: 课程名称
        year: 年份
        save_dir: 保存目录
        video_type: 视频类型

    返回:
        list: 待下载视频列表
    """
    rows = []
    current_time = time.time()

    for entry in tqdm(data, desc=f"检查 {course_code} 视频"):
        # 只处理已结束的课程
        if entry.get("endTime", {}).get("time", 0) / 1000 > current_time:
            continue

        # 解析时间信息
        start_time = entry["startTime"]
        month = start_time["month"] + 1  # API返回的月份比实际月份小1，需要+1修正
        date = start_time["date"]
        day = start_time["day"]
        jie = entry["jie"]
        days = entry["days"]

        # 检查文件是否已存在
        if is_video_exists(course_code, course_name, year, month, date, day, jie, days, save_dir, video_type):
            continue

        try:
            # 获取视频下载链接
            video_info = get_video_info_from_html(entry["id"])
            
            if not video_info:
                logger.debug(f"课程 {entry['id']} 没有可用的视频信息")
                continue

            # 正确提取视频链接 - 处理嵌套的videoPath结构
            video_path = video_info.get("videoPath", {})
            ppt_video = video_path.get("pptVideo", "")
            teacher_track = video_path.get("teacherTrack", "")

            # 按视频类型选择所需的链接
            if video_type == 'ppt':
                teacher_track = ''
            elif video_type == 'teacher':
                ppt_video = ''

            # 如果没有所需类型的视频链接，跳过
            if video_type == 'both' and not (ppt_video or teacher_track):
                continue
            elif video_type == 'ppt' and not ppt_video:
                continue
            elif video_type == 'teacher' and not teacher_track:
                continue

            # 添加到待下载列表
            rows.append([month, date, day, jie, days, ppt_video, teacher_track])

        except Exception as e:
            logger.error(f"获取课程 {entry['id']} 视频信息失败: {e}")
            continue

    return rows


def is_video_exists(course_code, course_name, year, month, date, day, jie, days, save_dir, video_type):
    """
    检查视频文件是否已存在。

    参数:
        course_code: 课程代码
        course_name: 课程名称
        year: 年份
        month: 月份
        date: 日期
        day: 星期
        jie: 节次
        days: 周数
        save_dir: 保存目录
        video_type: 视频类型

    返回:
        bool: 文件是否存在
    """
    day_chinese = day_to_chinese(day)
    base_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节"

    # 生成可能的文件名模式
    ppt_patterns = []
    teacher_patterns = []
    
    if video_type in ['both', 'ppt']:
        ppt_patterns = [
            f"{base_filename}-pptVideo.mp4",
            f"{base_filename}-pptVideo.ts",  # 向后兼容
            # 合并文件的可能名称
            f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-pptVideo.mp4",
            f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-pptVideo.mp4"
        ]
    
    if video_type in ['both', 'teacher']:
        teacher_patterns = [
            f"{base_filename}-teacherTrack.mp4",
            f"{base_filename}-teacherTrack.ts",  # 向后兼容
            # 合并文件的可能名称
            f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-teacherTrack.mp4",
            f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-teacherTrack.mp4"
        ]

    # 检查文件是否存在
    save_path = Path(save_dir)
    ppt_exists = any(save_path.joinpath(pattern).exists() for pattern in ppt_patterns) if ppt_patterns else False
    teacher_exists = any(save_path.joinpath(pattern).exists() for pattern in teacher_patterns) if teacher_patterns else False

    if video_type == 'both':
        return ppt_exists and teacher_exists
    elif video_type == 'ppt':
        return ppt_exists
    else:  # teacher
        return teacher_exists


def parse_arguments():
    """
    解析自动化下载程序的命令行参数。

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
