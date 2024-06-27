#!/usr/bin/env python3

import os
import csv
import time
from argparse import ArgumentParser
from tqdm import tqdm
import traceback
from utils import day_to_chinese, user_input_with_check, create_directory
from downloader import download_m3u8, merge_videos
from api import get_initial_data, get_m3u8_links

def main(liveid=None, command='', single=0, merge=True):
    if liveid and not isinstance(liveid, int):
        liveid = int(liveid)
    elif not liveid:
        liveid = int(user_input_with_check(
            "请输入 liveId：",
            lambda liveid: liveid.isdigit() and len(liveid) <= 10
        ))

        single = user_input_with_check(
            "是否仅下载单节课视频？输入 y 下载单节课，n 下载这门课所有视频，s 则仅下载单集（半节课）视频，直接回车默认单节课 (Y/n/s):",
            lambda single: single.lower() in ['', 'y', 'n', 's']
        ).lower()
        if single in ['', 'y']:
            single = 1
        elif single == 's':
            single = 2
        else:
            single = 0

        if single != 2:
            merge = user_input_with_check(
                "是否自动合并上下半节课视频？输入 y 合并，n 不合并，直接回车默认合并 (Y/n):",
                lambda merge: merge.lower() in ['', 'y', 'n']
            ).lower() != 'n'
    else:
        if single > 2:
            single = 2

    data = get_initial_data(liveid)

    if not data:
        print("没有找到数据，请检查 liveId 是否正确。")
        return

    if single:
        matching_entry = next(
            filter(lambda entry: entry["id"] == liveid, data))

        if not matching_entry:
            raise ValueError("No matching entry found for the specified liveId")

        if single == 1:
            start_time = matching_entry["startTime"]
            data = list(filter(
                lambda entry: entry["startTime"]["date"] == start_time["date"] and
                entry["startTime"]["month"] == start_time["month"],
                data))
        else:
            data = [matching_entry]

    first_entry = data[0]
    start_time = first_entry["startTime"]["time"]
    course_code = first_entry["courseCode"]
    course_name = first_entry["courseName"]

    start_time_unix = start_time / 1000
    start_time_struct = time.gmtime(start_time_unix)
    year = start_time_struct.tm_year

    save_dir = f"{year}年{course_code}{course_name}"
    create_directory(save_dir)

    csv_filename = f"{year}年{course_code}{course_name}.csv"

    rows = []
    for entry in tqdm(data, desc="获取视频链接"):
        live_id = entry["id"]
        days = entry["days"]
        day = entry["startTime"]["day"]
        jie = entry["jie"]

        start_time = entry["startTime"]["time"]
        start_time_unix = start_time / 1000
        start_time_struct = time.gmtime(start_time_unix)
        month = start_time_struct.tm_mon
        date = start_time_struct.tm_mday

        ppt_video, teacher_track = get_m3u8_links(live_id)

        row = [month, date, day, jie, days, ppt_video, teacher_track]
        rows.append(row)

    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['month', 'date', 'day', 'jie', 'days', 'pptVideo', 'teacherTrack'])
        writer.writerows(rows)

    print(f"{csv_filename} 文件已创建并写入数据。")

    def process_rows(rows):
        for i in range(0, len(rows), 2):
            row1 = rows[i]
            month1, date1, day1, jie1, days1, ppt_video1, teacher_track1 = row1
            day_chinese1 = day_to_chinese(day1)

            row2 = rows[i + 1] if i + 1 < len(rows) else None
            if row2:
                month2, date2, day2, jie2, days2, ppt_video2, teacher_track2 = row2
                day_chinese2 = day_to_chinese(day2)

            ppt_video_files = []
            if ppt_video1:
                filename1 = f"{course_code}{course_name}{year}年{month1}月{date1}日第{days1}周星期{day_chinese1}第{jie1}节-pptVideo.ts"
                filepath1 = os.path.join(save_dir, filename1)
                if not os.path.exists(filepath1):
                    download_m3u8(ppt_video1, filename1, save_dir, command=command)
                ppt_video_files.append(filepath1)

            if ppt_video2:
                filename2 = f"{course_code}{course_name}{year}年{month2}月{date2}日第{days2}周星期{day_chinese2}第{jie2}节-pptVideo.ts"
                filepath2 = os.path.join(save_dir, filename2)
                if not os.path.exists(filepath2):
                    download_m3u8(ppt_video2, filename2, save_dir, command=command)
                ppt_video_files.append(filepath2)

            if len(ppt_video_files) == 2 and merge:
                ppt_merged_filename = f"{course_code}{course_name}{year}年{month1}月{date1}日第{days1}周星期{day_chinese1}第{jie1}-{jie2}节-pptVideo.ts"
                ppt_merged_filepath = os.path.join(save_dir, ppt_merged_filename)
                merge_videos(ppt_video_files, ppt_merged_filepath)

            teacher_track_files = []
            if teacher_track1:
                filename1 = f"{course_code}{course_name}{year}年{month1}月{date1}日第{days1}周星期{day_chinese1}第{jie1}节-teacherTrack.ts"
                filepath1 = os.path.join(save_dir, filename1)
                if not os.path.exists(filepath1):
                    download_m3u8(teacher_track1, filename1, save_dir, command=command)
                teacher_track_files.append(filepath1)

            if teacher_track2:
                filename2 = f"{course_code}{course_name}{year}年{month2}月{date2}日第{days2}周星期{day_chinese2}第{jie2}节-teacherTrack.ts"
                filepath2 = os.path.join(save_dir, filename2)
                if not os.path.exists(filepath2):
                    download_m3u8(teacher_track2, filename2, save_dir, command=command)
                teacher_track_files.append(filepath2)

            if len(teacher_track_files) == 2 and merge:
                teacher_merged_filename = f"{course_code}{course_name}{year}年{month1}月{date1}日第{days1}周星期{day_chinese1}第{jie1}-{jie2}节-teacherTrack.ts"
                teacher_merged_filepath = os.path.join(save_dir, teacher_merged_filename)
                merge_videos(teacher_track_files, teacher_merged_filepath)

    if single == 1:
        process_rows(rows[:2])
    elif single == 2:
        row = rows[0]
        month, date, day, jie, days, ppt_video, teacher_track = row
        day_chinese = day_to_chinese(day)

        if ppt_video:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo.ts"
            filepath = os.path.join(save_dir, filename)
            if not os.path.exists(filepath):
                download_m3u8(ppt_video, filename, save_dir, command=command)

        if teacher_track:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-teacherTrack.ts"
            filepath = os.path.join(save_dir, filename)
            if not os.path.exists(filepath):
                download_m3u8(teacher_track, filename, save_dir, command=command)

    else:
        process_rows(rows)

    print("所有视频下载和处理完成。")

def parse_arguments():
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('liveid', nargs='?', default=None, help="课程的 liveId，不输入则采用交互式方式获取")
    parser.add_argument('-c', '--command', default='', help="自定义下载命令，使用 {url}, {save_dir}, {filename} 作为替换标记")
    parser.add_argument('-s', '--single', action='count', default=0, help="仅下载单节课视频（-s：单节课视频，-ss：半节课视频）")
    parser.add_argument('--no-merge', action='store_false', help="不合并上下半节课视频")

    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    try:
        main(liveid=args.liveid, command=args.command, single=args.single, merge=args.no_merge)
    except Exception as e:
        print(f"发生错误：{e}")
        print(traceback.format_exc())
