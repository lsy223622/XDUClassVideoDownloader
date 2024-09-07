#!/usr/bin/env python3

import requests
import time
import os
import csv
from tqdm import tqdm
import traceback
from utils import day_to_chinese, create_directory, write_config, read_config, handle_exception
from downloader import download_m3u8, merge_videos, process_rows
from api import get_initial_data, get_m3u8_links, scan_courses
import configparser
from argparse import ArgumentParser

CONFIG_FILE = 'config.ini'

def main():
    args = parse_arguments()
    config = configparser.ConfigParser()

    current_time = time.localtime()
    term_year = current_time.tm_year
    month = current_time.tm_mon

    term_id = 1 if month >= 9 else 2
    if month < 2:
        term_year -= 1

    if not os.path.exists(CONFIG_FILE):
        user_id = args.uid or input("请输入用户ID：")
        term_year = args.year or term_year
        term_id = args.term or term_id
        courses = scan_courses(user_id, term_year, term_id)
        write_config(config, user_id, courses)
        print("配置文件已生成，请修改配置文件后按回车继续...")
        input()
    else:
        config = read_config()
        user_id = args.uid or config['DEFAULT']['user_id']
        term_year = args.year or config['DEFAULT'].get('term_year', term_year)
        term_id = args.term or config['DEFAULT'].get('term_id', term_id)
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
                    'course_name': course['courseName'],
                    'live_id': course['id'],
                    'download': 'yes'
                }
                new_course_added = True
            else:
                # 检查现有课程的详细信息是否匹配
                existing_course = existing_courses[course_id_str]
                if (existing_course['course_code'] != course['courseCode'] or
                    existing_course['course_name'] != course['courseName'] or
                    existing_course['live_id'] != str(course['id'])):
                    print(f"更新课程信息：{course_id_str} - {course['courseName']}")
                    config[course_id_str] = {
                        'course_code': course['courseCode'],
                        'course_name': course['courseName'],
                        'live_id': course['id'],
                        'download': existing_course.get('download', 'yes')
                    }
                    new_course_added = True

        with open(CONFIG_FILE, 'w') as configfile:
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
        course_name = config[course_id]['course_name']
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

        rows = []
        for entry in tqdm(data, desc=f"获取 {course_code} - {course_name} 的视频链接"):
            if entry["endTime"]["time"] / 1000 > time.time():
                continue

            try:
                ppt_video, teacher_track = get_m3u8_links(entry["id"])
            except ValueError as e:
                print(f"获取视频链接时发生错误：{e}，liveId: {entry['id']}")
                ppt_video, teacher_track = '', ''

            start_time_struct = time.gmtime(entry["startTime"]["time"] / 1000)
            rows.append([
                start_time_struct.tm_mon, start_time_struct.tm_mday, 
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
            print(f"课程 {course_code} - {course_name} 没有视频。")

    # 下载视频
    for course_code, course_info in all_videos.items():
        course_name = course_info["course_name"]
        year = course_info["year"]
        rows = course_info["rows"]
        save_dir = f"{year}年{course_code}{course_name}"
        create_directory(save_dir)
        process_rows(rows, course_code, course_name, year, save_dir)

    print("所有视频下载和处理完成。")

def parse_arguments():
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('-u', '--uid', default=None, help="用户的 UID")
    parser.add_argument('-y', '--year', type=int, default=None, help="学年")
    parser.add_argument('-t', '--term', type=int, choices=[1, 2], default=None, help="学期")
    return parser.parse_args()

if __name__ == "__main__":
    main()
