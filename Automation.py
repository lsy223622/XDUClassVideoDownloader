#!/usr/bin/env python3

import os
import time
import traceback
import configparser
from tqdm import tqdm
from argparse import ArgumentParser
from api import get_initial_data, get_m3u8_links, scan_courses, check_update
from downloader import process_rows
from utils import create_directory, write_config, read_config, handle_exception, day_to_chinese, remove_invalid_chars

check_update()

CONFIG_FILE = 'config.ini'

def main():
    args = parse_arguments()
    config = configparser.ConfigParser()

    current_time = time.localtime()
    term_year = current_time.tm_year
    month = current_time.tm_mon

    term_id = 1 if month >= 9 else 2
    if month < 8:
        term_year -= 1

    if not os.path.exists(CONFIG_FILE):
        user_id = args.uid or input("请输入用户ID：")
        term_year = args.year or term_year
        term_id = args.term or term_id
        video_type = args.video_type
        courses = scan_courses(user_id, term_year, term_id)
        write_config(config, user_id, courses, video_type)
        print("配置文件已生成，请修改配置文件后按回车继续...")
        input()
    else:
        config = read_config()
        user_id = args.uid or config['DEFAULT']['user_id']
        term_year = args.year or config['DEFAULT'].get('term_year', term_year)
        term_id = args.term or config['DEFAULT'].get('term_id', term_id)
        # 处理旧配置文件兼容性，添加默认video_type
        # 命令行参数优先，如果没有指定则使用配置文件中的值
        video_type = args.video_type or config['DEFAULT'].get('video_type', 'both')
        
        # 如果配置文件中没有video_type，自动添加
        if 'video_type' not in config['DEFAULT']:
            config['DEFAULT']['video_type'] = 'both'
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            print("已自动更新配置文件，添加视频类型选项（默认：两种视频都下载）")
        
        print("使用配置文件中的用户ID：", user_id)
        existing_courses = {section: dict(config[section]) for section in config.sections() if section != 'DEFAULT'}
        new_courses = scan_courses(user_id, term_year, term_id)
        new_course_added = False
        for course_id, course in new_courses.items():
            course_id_str = str(course_id)  # 将course_id转换为字符串类型
            if course_id_str not in config.sections():
                print(f"添加新课程：{course_id_str} - {course['courseName']}")
                config[course_id_str] = {
                    'course_code': course['courseCode'],
                    'course_name': remove_invalid_chars(course['courseName']),
                    'live_id': course['id'],
                    'download': 'yes'
                }
                new_course_added = True
            else:
                # 检查现有课程的详细信息是否匹配
                existing_course = existing_courses[course_id_str]
                if (existing_course['course_code'] != course['courseCode'] or
                    existing_course['course_name'] != remove_invalid_chars(course['courseName']) or
                    existing_course['live_id'] != str(course['id'])):
                    print(f"更新课程信息：{course_id_str} - {course['courseName']}")
                    config[course_id_str] = {
                        'course_code': course['courseCode'],
                        'course_name': remove_invalid_chars(course['courseName']),
                        'live_id': course['id'],
                        'download': existing_course.get('download', 'yes')
                    }
                    new_course_added = True

        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

        if new_course_added:
            print("配置文件已更新，请修改配置文件后按回车继续...")
            input()

    # 重新读取配置文件
    config = read_config()

    all_videos = {}
    for course_id in config.sections():
        if course_id == 'DEFAULT' or config[course_id].get('download') != 'yes':
            continue

        course_code = config[course_id]['course_code']
        course_name = remove_invalid_chars(config[course_id]['course_name'])
        live_id = config[course_id]['live_id']
        print(f"正在检查课程：{course_code} - {course_name}")

        try:
            data = get_initial_data(live_id)
        except Exception as e:
            handle_exception(e, "获取初始数据时发生错误")
            continue

        if not data:
            print(f"没有找到数据，请检查 liveId 是否正确。liveId: {live_id}")
            continue

        year = time.gmtime(data[0]["startTime"]["time"] / 1000).tm_year
        save_dir = f"{year}年{course_code}{course_name}"
        create_directory(save_dir)

        rows = []
        for entry in tqdm(data, desc=f"获取 {course_code} - {course_name} 的视频链接"):
            if entry["endTime"]["time"] / 1000 > time.time():
                continue
            
            start_time_struct = time.gmtime(entry["startTime"]["time"] / 1000)
            month, date = start_time_struct.tm_mon, start_time_struct.tm_mday
            day = entry["startTime"]["day"]
            jie = entry["jie"]
            days = entry["days"]
            
            # 检查文件是否已存在
            day_chinese = day_to_chinese(day)
            base_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节"
            
            # 检查各种可能的文件名
            file_exists = any([
                os.path.exists(os.path.join(save_dir, f"{base_filename}-pptVideo.ts")),
                os.path.exists(os.path.join(save_dir, f"{base_filename}-teacherTrack.ts")),
                os.path.exists(os.path.join(save_dir, f"{base_filename}-pptVideo.mp4")),
                os.path.exists(os.path.join(save_dir, f"{base_filename}-teacherTrack.mp4")),
                # 检查合并文件
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-pptVideo.ts")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-pptVideo.ts")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-teacherTrack.ts")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-teacherTrack.ts")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-pptVideo.mp4")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-pptVideo.mp4")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{int(jie)-1}-{jie}节-teacherTrack.mp4")),
                os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{int(jie)+1}节-teacherTrack.mp4"))
            ])
            
            if file_exists:
                continue

            try:
                ppt_video, teacher_track = get_m3u8_links(entry["id"])
            except ValueError as e:
                print(f"获取视频链接时发生错误：{e}，liveId: {entry['id']}")
                ppt_video, teacher_track = '', ''

            rows.append([
                month, date, 
                entry["startTime"]["day"], entry["jie"], entry["days"], 
                ppt_video, teacher_track
            ])

        if rows:
            all_videos[course_code] = {
                "course_name": course_name,
                "year": year,
                "rows": rows
            }
        else:
            print(f"课程 {course_code} - {course_name} 没有或没有新增视频。")

    # 下载视频
    for course_code, course_info in all_videos.items():
        course_name = course_info["course_name"]
        year = course_info["year"]
        rows = course_info["rows"]
        save_dir = f"{year}年{course_code}{course_name}"
        create_directory(save_dir)
        process_rows(rows, course_code, course_name, year, save_dir, command='', merge=True, video_type=video_type)

    print("所有视频下载和处理完成。")

def parse_arguments():
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('-u', '--uid', default=None, help="用户的 UID")
    parser.add_argument('-y', '--year', type=int, default=None, help="学年")
    parser.add_argument('-t', '--term', type=int, choices=[1, 2], default=None, help="学期")
    parser.add_argument('--video-type', choices=['both', 'ppt', 'teacher'], default='both', help="选择要下载的视频类型：both（两种都下载，默认）、ppt（仅下载pptVideo）、teacher（仅下载teacherTrack）")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    try:
        main()
    except Exception as e:
        print(f"发生错误：{e}")
        print(traceback.format_exc())
