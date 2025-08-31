#!/usr/bin/env python3
import os
import csv
import time
import traceback
from tqdm import tqdm
from argparse import ArgumentParser
from api import get_initial_data, get_m3u8_links, check_update, fetch_m3u8_links
from downloader import download_m3u8, process_rows
from utils import day_to_chinese, user_input_with_check, create_directory, handle_exception, remove_invalid_chars, calculate_optimal_threads
import concurrent.futures
from threading import Lock

check_update()

def main(liveid=None, command='', single=0, merge=True, video_type='both'):
    if not liveid:
        liveid = int(user_input_with_check("请输入 liveId：", lambda x: x.isdigit() and len(x) <= 10))
        single = user_input_with_check("是否仅下载单节课视频？输入 y 下载单节课，n 下载这门课所有视频，s 则仅下载单集（半节课）视频，直接回车默认单节课 (Y/n/s):", lambda x: x.lower() in ['', 'y', 'n', 's']).lower()
        single = 1 if single in ['', 'y'] else 2 if single == 's' else 0
        merge = user_input_with_check("是否自动合并上下半节课视频？(Y/n):", lambda x: x.lower() in ['', 'y', 'n']).lower() != 'n'
        video_type_input = user_input_with_check("选择要下载的视频类型？输入 b 下载两种视频，p 仅下载pptVideo，t 仅下载teacherTrack，直接回车默认两种都下载 (B/p/t):", lambda x: x.lower() in ['', 'b', 'p', 't']).lower()
        video_type = 'ppt' if video_type_input == 'p' else 'teacher' if video_type_input == 't' else 'both'
        # 跳过一定的周数，直到大于此值
        skip_input = user_input_with_check(
            "是否从某个周数才开始下载？输入周数（如 3 则从第三周开始下载）或直接回车表示从第一周开始：",
            lambda x: x.isdigit() or x == ''
        ).strip()
        skip_until = int(skip_input) - 1 if skip_input.isdigit() else 0
        if skip_until < 0:
            raise ValueError("跳过的周数不能为负数")
    else:
        liveid = int(liveid) if not isinstance(liveid, int) else liveid
        single = min(single, 2)
        # 非交互模式下，默认不跳过任何周
        skip_until = 0

    try:
        data = get_initial_data(liveid)
    except Exception as e:
        handle_exception(e, "获取初始数据时发生错误")
        return

    if not data:
        print("没有找到数据，请检查 liveId 是否正确。")
        return

    if single:
        data_temp = data[:] # 切片拷贝
        data = [entry for entry in data_temp if entry["id"] == liveid]
        if not data:
            raise ValueError("No matching entry found for the specified liveId")
        if single == 1:
            start_time = data[0]["startTime"]
            data = [entry for entry in data_temp if entry["startTime"]["date"] == start_time["date"] and entry["startTime"]["month"] == start_time["month"]]

    first_entry = data[0]
    year = time.gmtime(first_entry["startTime"]["time"] / 1000).tm_year
    course_code = first_entry["courseCode"]
    course_name = remove_invalid_chars(first_entry["courseName"])
    save_dir = f"{year}年{course_code}{course_name}"
    create_directory(save_dir)
    csv_filename = f"{save_dir}.csv"

    rows = []
    lock = Lock()
    with tqdm(total=len(data), desc="获取视频链接") as desc:
        max_threads = calculate_optimal_threads()
        print(f"CPU 核心数: {os.cpu_count()}, 最佳线程数: {max_threads}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [executor.submit(fetch_m3u8_links, entry, lock, desc) for entry in data if entry["endTime"]["time"] / 1000 <= time.time()]
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                if row:
                    rows.append(row)

    rows.sort(key=lambda x: (x[0], x[1], x[2], int(x[3]), x[4])) # 确保按时间排序(确保'jie'是整数)

    # 根据 skip_until 过滤掉周数 <= skip_until 的行
    if skip_until > 0:
        rows = [row for row in rows if int(row[4]) > skip_until]

    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['month', 'date', 'day', 'jie', 'days', 'pptVideo', 'teacherTrack'])
        writer.writerows(rows)

    print(f"{csv_filename} 文件已创建并写入数据。")

    if single == 1:
        process_rows(rows[:2], course_code, course_name, year, save_dir, command, merge, video_type)
    elif single == 2:
        row = rows[0]
        month, date, day, jie, days, ppt_video, teacher_track = row
        day_chinese = day_to_chinese(day)
        if video_type in ['both', 'ppt'] and ppt_video:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo.ts"
            filepath = os.path.join(save_dir, filename)
            if not os.path.exists(filepath):
                download_m3u8(ppt_video, filename, save_dir, command=command)
        if video_type in ['both', 'teacher'] and teacher_track:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-teacherTrack.ts"
            filepath = os.path.join(save_dir, filename)
            if not os.path.exists(filepath):
                download_m3u8(teacher_track, filename, save_dir, command=command)
    else:
        process_rows(rows, course_code, course_name, year, save_dir, command, merge, video_type)

    print("所有视频下载和处理完成。")


def parse_arguments():
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('liveid', nargs='?', default=None, help="课程的 liveId，不输入则采用交互式方式获取")
    parser.add_argument('-c', '--command', default='', help="自定义下载命令，使用 {url}, {save_dir}, {filename} 作为替换标记")
    parser.add_argument('-s', '--single', action='count', default=0, help="仅下载单节课视频（-s：单节课视频，-ss：半节课视频）")
    parser.add_argument('--no-merge', action='store_false', help="不合并上下半节课视频")
    parser.add_argument('--video-type', choices=['both', 'ppt', 'teacher'], default='both', help="选择要下载的视频类型：both（两种都下载，默认）、ppt（仅下载pptVideo）、teacher（仅下载teacherTrack）")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    try:
        
        main(liveid=args.liveid, command=args.command, single=args.single, merge=args.no_merge, video_type=args.video_type)
    except Exception as e:
        print(f"发生错误：{e}")
        print(traceback.format_exc())