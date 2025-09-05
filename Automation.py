#!/usr/bin/env python3
"""
西安电子科技大学录直播平台课程视频下载器 - 自动化批量下载程序
用于自动扫描和下载用户的所有课程视频
"""

import os
import time
import traceback
import sys
import configparser
from tqdm import tqdm
from argparse import ArgumentParser
from api import get_initial_data, get_m3u8_links, scan_courses, check_update
from downloader import process_rows
from utils import create_directory, write_config, read_config, handle_exception, day_to_chinese, remove_invalid_chars

# 程序启动时检查更新
check_update()

# 配置文件名
CONFIG_FILE = 'config.ini'


def main():
    """
    自动化下载主函数：扫描用户的所有课程并批量下载视频。

    功能流程：
    1. 解析命令行参数或读取配置文件
    2. 扫描用户的所有课程
    3. 更新配置文件（如有新课程）
    4. 批量下载所有启用下载的课程视频
    """
    # 解析命令行参数
    args = parse_arguments()
    config = configparser.ConfigParser()

    # 获取当前时间用于确定学期
    current_time = time.localtime()
    term_year = current_time.tm_year
    month = current_time.tm_mon

    # 根据月份确定学期：9月及以后为第一学期，3月及以后为第二学期
    term_id = 1 if month >= 9 or month < 3 else 2
    if month < 9:  # 1-8月属于上一学年
        term_year -= 1

    # 首次运行：创建配置文件
    if not os.path.exists(CONFIG_FILE):
        # 获取用户输入或使用命令行参数
        user_id = args.uid or input("请输入用户ID：")
        term_year = args.year or term_year
        term_id = args.term or term_id
        video_type = args.video_type if args.video_type is not None else 'both'

        # 提示正在生成配置文件，避免用户误以为程序卡住
        print("正在生成配置文件...", end='', flush=True)
        try:
            # 扫描课程并写入配置文件
            courses = scan_courses(user_id, term_year, term_id)
            write_config(config, user_id, courses, video_type)
        except Exception as e:
            # 在发生异常时清理提示行并打印错误信息
            sys.stdout.write('\r' + ' ' * 80 + '\r')
            print(f"生成配置文件时发生错误：{e}")
            raise
        # 覆盖掉正在生成的提示并显示已生成消息
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        print("配置文件已生成，请修改配置文件后按回车继续...")
        input()  # 等待用户确认配置
    else:
        # 已存在配置文件：读取并更新
        config = read_config()
        user_id = args.uid or config['DEFAULT']['user_id']
        term_year = args.year or config['DEFAULT'].get('term_year', term_year)
        term_id = args.term or config['DEFAULT'].get('term_id', term_id)

        # 处理旧配置文件兼容性，添加默认video_type
        video_type = args.video_type if args.video_type is not None else config['DEFAULT'].get('video_type', 'both')

        # 如果配置文件中没有video_type，自动添加
        if 'video_type' not in config['DEFAULT']:
            config['DEFAULT']['video_type'] = 'both'
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            print("已自动更新配置文件，添加视频类型选项（默认：两种视频都下载）")

        print("使用配置文件中的用户ID：", user_id)

        # 在重新扫描课程前显示覆盖式提示，避免用户误以为程序卡住
        print("正在扫描课程...", end='', flush=True)

        # 读取现有课程配置
        existing_courses = {section: dict(
            config[section]) for section in config.sections() if section != 'DEFAULT'}

        # 重新扫描课程，检查是否有新课程
        try:
            new_courses = scan_courses(user_id, term_year, term_id)
        finally:
            # 清除覆盖式提示行，后续的打印信息（如添加/更新课程）会显示在新行
            sys.stdout.write('\r' + ' ' * 80 + '\r')
        new_course_added = False

        # 处理新发现的课程
        for course_id, course in new_courses.items():
            course_id_str = str(course_id)  # 将course_id转换为字符串类型
            if course_id_str not in config.sections():
                # 添加新课程
                print(f"添加新课程：{course_id_str} - {course['courseName']}")
                config[course_id_str] = {
                    'course_code': course['courseCode'],
                    'course_name': remove_invalid_chars(course['courseName']),
                    'live_id': course['id'],
                    'download': 'yes'
                }
                new_course_added = True
            else:
                # 检查现有课程的详细信息是否需要更新
                existing_course = existing_courses[course_id_str]
                if (existing_course['course_code'] != course['courseCode'] or
                    existing_course['course_name'] != remove_invalid_chars(course['courseName']) or
                        existing_course['live_id'] != str(course['id'])):
                    print(f"更新课程信息：{course_id_str} - {course['courseName']}")
                    config[course_id_str] = {
                        'course_code': course['courseCode'],
                        'course_name': remove_invalid_chars(course['courseName']),
                        'live_id': course['id'],
                        # 保持原有的下载设置
                        'download': existing_course.get('download', 'yes')
                    }
                    new_course_added = True

        # 保存更新后的配置文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

        # 如果有新课程，提示用户检查配置
        if new_course_added:
            print("配置文件已更新，请修改配置文件后按回车继续...")
            input()

    # 重新读取配置文件以获取最新配置
    config = read_config()
    video_type = args.video_type if args.video_type is not None else config['DEFAULT'].get('video_type', 'both')

    # 批量处理所有启用下载的课程
    all_videos = {}
    for course_id in config.sections():
        # 跳过DEFAULT段和未启用下载的课程
        if course_id == 'DEFAULT' or config[course_id].get('download') != 'yes':
            continue

        # 获取课程信息
        course_code = config[course_id]['course_code']
        course_name = remove_invalid_chars(config[course_id]['course_name'])
        live_id = config[course_id]['live_id']
        print(f"正在检查课程：{course_code} - {course_name}")

        try:
            # 获取课程数据
            data = get_initial_data(live_id)
        except Exception as e:
            handle_exception(e, "获取初始数据时发生错误")
            continue  # 跳过此课程，继续处理下一个

        if not data:
            print(f"没有找到数据，请检查 liveId 是否正确。liveId: {live_id}")
            continue

        # 提取课程年份并创建保存目录
        year = time.gmtime(data[0]["startTime"]["time"] / 1000).tm_year
        save_dir = f"{year}年{course_code}{course_name}"
        create_directory(save_dir)

        # 处理每个课程条目，获取视频链接
        rows = []
        for entry in tqdm(data, desc=f"获取 {course_code} - {course_name} 的视频链接"):
            # 只处理已结束的课程
            if entry["endTime"]["time"] / 1000 > time.time():
                continue

            # 解析时间信息
            start_time_struct = time.gmtime(entry["startTime"]["time"] / 1000)
            month, date = start_time_struct.tm_mon, start_time_struct.tm_mday
            day = entry["startTime"]["day"]
            jie = entry["jie"]
            days = entry["days"]

            # 检查文件是否已存在，避免重复下载
            day_chinese = day_to_chinese(day)
            base_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节"

            # 根据 video_type 选择要检查的文件类型
            # 拆分为 ppt 与 teacher 两类，方便在 both 模式下做“部分存在仍需继续”的判断
            ppt_patterns = []
            teacher_patterns = []
            if video_type in ['both', 'ppt']:
                ppt_patterns = [
                    f"{base_filename}-pptVideo.mp4",
                    f"{base_filename}-pptVideo.ts",  # 向后兼容
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-pptVideo.mp4",
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-pptVideo.ts",
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-pptVideo.mp4",
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-pptVideo.ts"
                ]
            if video_type in ['both', 'teacher']:
                teacher_patterns = [
                    f"{base_filename}-teacherTrack.mp4",
                    f"{base_filename}-teacherTrack.ts",  # 向后兼容
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-teacherTrack.mp4",
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-teacherTrack.ts",
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-teacherTrack.mp4",
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-teacherTrack.ts"
                ]

            ppt_exists = any(os.path.exists(os.path.join(save_dir, f))
                             for f in ppt_patterns) if ppt_patterns else False
            teacher_exists = any(os.path.exists(os.path.join(save_dir, f))
                                 for f in teacher_patterns) if teacher_patterns else False

            if video_type == 'both':
                # both 模式：只有两种都存在才整体跳过；如果只存在其中一种则继续处理缺失的那一种
                file_exists = ppt_exists and teacher_exists
            elif video_type == 'ppt':
                file_exists = ppt_exists
            else:  # video_type == 'teacher'
                file_exists = teacher_exists

            # 如果文件已存在，跳过此条目
            if file_exists:
                continue

            try:
                # 获取视频下载链接（同时拿到两个，后面按需裁剪）
                ppt_video, teacher_track = get_m3u8_links(entry["id"])
            except ValueError as e:
                print(f"获取视频链接时发生错误：{e}，liveId: {entry['id']}")
                ppt_video, teacher_track = '', ''

            # 按视频类型选择保留所需的链接，避免传递无关类型
            if video_type == 'ppt':
                teacher_track = ''
            elif video_type == 'teacher':
                ppt_video = ''

            # 添加到待下载列表：结构保持不变 [.., ppt_video, teacher_track]
            rows.append([
                month, date,
                entry["startTime"]["day"], entry["jie"], entry["days"],
                ppt_video, teacher_track
            ])

        # 如果有新视频需要下载，加入下载队列
        if rows:
            all_videos[course_code] = {
                "course_name": course_name,
                "year": year,
                "rows": rows
            }
        else:
            print(f"课程 {course_code} - {course_name} 没有或没有新增视频。")

    # 批量下载所有课程的视频
    for course_code, course_info in all_videos.items():
        course_name = course_info["course_name"]
        year = course_info["year"]
        rows = course_info["rows"]
        save_dir = f"{year}年{course_code}{course_name}"
        create_directory(save_dir)
        # 使用统一的处理函数下载视频
        process_rows(rows, course_code, course_name, year, save_dir,
                     command='', merge=True, video_type=video_type)

    print("所有视频下载和处理完成。")


def parse_arguments():
    """
    解析自动化下载程序的命令行参数。

    返回:
        argparse.Namespace: 包含所有命令行参数的对象
    """
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('-u', '--uid', default=None, help="用户的 UID")
    parser.add_argument('-y', '--year', type=int, default=None, help="学年")
    parser.add_argument('-t', '--term', type=int,
                        choices=[1, 2], default=None, help="学期")
    parser.add_argument('--video-type', choices=['both', 'ppt', 'teacher'], default=None,
                        help="选择要下载的视频类型：both（两种都下载=）、ppt（仅下载pptVideo）、teacher（仅下载teacherTrack）")
    return parser.parse_args()


if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    try:
        # 调用主函数开始自动化下载
        main()
    except Exception as e:
        # 捕获并显示所有未处理的异常
        print(f"发生错误：{e}")
        print(traceback.format_exc())
