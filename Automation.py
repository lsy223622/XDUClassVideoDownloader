#!/usr/bin/env python3

import requests
import time
import os
import csv
from tqdm import tqdm
import traceback
from utils import day_to_chinese, create_directory
from downloader import download_m3u8, merge_videos, process_rows
from api import get_initial_data, get_m3u8_links, fetch_data

def main():
    user_id = input("请输入用户ID：")
    current_time = time.localtime()
    year = current_time.tm_year
    month = current_time.tm_mon

    if month >= 9:
        term_id = 1
    elif month >= 2:
        term_id = 2
    else:
        term_id = 2
        year -= 1

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": "UID=2"
    }

    week = 1
    consecutive_empty_weeks = 0
    first_classes = {}
    all_videos = {}

    while consecutive_empty_weeks < 2:
        url = f"https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage?fid=16820&userId={user_id}&week={week}&termYear={year}&termId={term_id}"
        data = fetch_data(url, headers)
        
        if data and len(data) > 0:
            for item in data:
                course_id = item['courseId']
                if course_id not in first_classes:
                    first_classes[course_id] = item
            consecutive_empty_weeks = 0
        else:
            consecutive_empty_weeks += 1
        
        week += 1

    print("本学期有以下课程：")
    for course_id, first_class in first_classes.items():
        print(f"{first_class['courseCode']} - {first_class['courseName']}")

    for course_id, first_class in first_classes.items():
        live_id = first_class['id']
        course_code = first_class['courseCode']
        course_name = first_class['courseName']
        print(f"正在检查课程：{course_code} - {course_name}")
        
        try:
            data = get_initial_data(live_id)
        except Exception as e:
            print(f"获取初始数据时发生错误：{e}")
            continue

        if not data:
            print(f"没有找到数据，请检查 liveId 是否正确。liveId: {live_id}")
            continue

        first_entry = data[0]
        start_time = first_entry["startTime"]["time"]
        course_code = first_entry["courseCode"]
        course_name = first_entry["courseName"]

        start_time_unix = start_time / 1000
        start_time_struct = time.gmtime(start_time_unix)
        year = start_time_struct.tm_year

        rows = []
        for entry in tqdm(data, desc=f"获取 {course_code} - {course_name} 的视频链接"):
            live_id = entry["id"]
            days = entry["days"]
            day = entry["startTime"]["day"]
            jie = entry["jie"]

            start_time = entry["startTime"]["time"]
            start_time_unix = start_time / 1000
            start_time_struct = time.gmtime(start_time_unix)
            month = start_time_struct.tm_mon
            date = start_time_struct.tm_mday

            # 检查视频是否在未来
            if start_time_unix > time.time():
                continue

            try:
                ppt_video, teacher_track = get_m3u8_links(live_id)
            except ValueError as e:
                print(f"获取视频链接时发生错误：{e}，liveId: {live_id}")
                ppt_video, teacher_track = '', ''

            row = [month, date, day, jie, days, ppt_video, teacher_track]
            rows.append(row)

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

if __name__ == "__main__":
    main()
