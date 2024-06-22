#!/usr/bin/env python3

import requests
import json
import csv
import urllib.parse
import subprocess
import time
from tqdm import tqdm
import os
from argparse import ArgumentParser
import traceback
import sys


def get_initial_data(liveid):
    url = "http://newesxidian.chaoxing.com/live/listSignleCourse"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": "UID=2"
    }
    data = {
        "liveId": liveid
    }

    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()


def get_m3u8_links(live_id):
    url = f"http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId={live_id}&status=2"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": "UID=2"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    response_text = response.text

    url_start = response_text.find('info=')
    if url_start == -1:
        raise ValueError("info parameter not found in the response")

    encoded_info = response_text[url_start + 5:]
    decoded_info = urllib.parse.unquote(encoded_info)
    info_json = json.loads(decoded_info)

    video_paths = info_json.get('videoPath', {})
    ppt_video = video_paths.get('pptVideo', '')
    teacher_track = video_paths.get('teacherTrack', '')

    return ppt_video, teacher_track


def download_m3u8(url, filename, save_dir, command=''):
    if not command:
        if sys.platform.startswith('win32'):
            command = f'N_m3u8DL-RE.exe "{url}" --save-dir "{save_dir}" --save-name "{filename}" --check-segments-count False --binary-merge True'
        else:
            command = f'./N_m3u8DL-RE "{url}" --save-dir "{save_dir}" --save-name "{filename}" --check-segments-count False --binary-merge True'
    else:
        command = command.format(url=url, filename=filename, save_dir=save_dir)

    # TODO: make this configurable
    for attempt in range(2):
        try:
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError:
            print(f"第{attempt+1}次下载 {filename} 出错：\n{traceback.format_exc()}\n重试中...")


def day_to_chinese(day):
    days = ["日", "一", "二", "三", "四", "五", "六"]
    return days[day]


def user_input_with_check(prompt, check_func):
    while True:
        user_input = input(prompt)
        if check_func(user_input):
            return user_input
        else:
            print("输入错误，请重新输入：")


def main(liveid=None, command='', single=0):
    if not liveid:
        # if liveid is not specified, default to interactive mode for all inputs
        liveid = int(user_input_with_check(
            "请输入 liveId：",
            lambda liveid: liveid.isdigit() and len(liveid) <= 10
        ))

        single = user_input_with_check(
            "是否仅下载单节课视频？输入s则仅下载单集视频(Y/n/s)：",
            lambda single: single.lower() in ['', 'y', 'n', 's']
        ).lower()
        if single in ['', 'y']:
            single = 1
        elif single == 's':
            single = 2
        else:
            single = 0
    else:
        # dealing with naughty user here
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
            # how is this possible
            raise ValueError(
                "No matching entry found for the specified liveId")

        if single == 1:
            # use start time to find other entries in single course
            start_time = matching_entry["startTime"]
            # FIXME: is list needed?
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
    os.makedirs(save_dir, exist_ok=True)

    csv_filename = f"{year}年{course_code}{course_name}.csv"

    rows = []
    for entry in tqdm(data, desc="获取视频链接"):
        live_id = entry["id"]
        days = entry["days"]  # week number
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

    for row in tqdm(rows, desc="Downloading videos"):
        month, date, day, jie, days, ppt_video, teacher_track = row
        day_chinese = day_to_chinese(day)

        if ppt_video:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo"
            filepath = os.path.join(save_dir, f"{filename}.ts")
            if os.path.exists(filepath):
                print(f"{filepath} 已存在，跳过下载。")
            else:
                download_m3u8(ppt_video, filename, save_dir, command=command)

        if teacher_track:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-teacherTrack"
            filepath = os.path.join(save_dir, f"{filename}.ts")
            if os.path.exists(filepath):
                print(f"{filepath} 已存在，跳过下载。")
            else:
                download_m3u8(teacher_track, filename, save_dir, command=command)

    print("所有视频下载完成。")


def parse_arguments():
    parser = ArgumentParser(description='用于下载西安电子科技大学录直播平台课程视频的工具')
    parser.add_argument('liveid', nargs='?', type=int, default=None, help='直播ID，不输入则采用交互式方式获取')
    parser.add_argument('-c', '--command', default='', help='自定义下载命令，使用 {url}, {save_dir}, {filename} 作为替换标记')
    parser.add_argument('-s', '--single', default=0, action='count', help='仅下载单节课视频，指定两次可以仅下载单集视频')

    args = parser.parse_args()
    return args


if __name__ == "__main__":
    args = parse_arguments()
    main(liveid=args.liveid, command=args.command, single=args.single)
