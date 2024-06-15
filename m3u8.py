import requests
import json
import csv
import urllib.parse
import subprocess
import time
from tqdm import tqdm
import os

def get_initial_data(input_live_id):
    url = "http://newesxidian.chaoxing.com/live/listSignleCourse"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": "UID=2"
    }
    data = {
        "liveId": input_live_id
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

def download_m3u8(url, filename, save_dir):
    command = f'N_m3u8DL-RE.exe "{url}" --save-dir "{save_dir}" --save-name "{filename}" --check-segments-count False --binary-merge True'
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError:
        print(f"初次下载 {filename} 出错，重试中...")
        try:
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError:
            print(f"重试下载 {filename} 仍然出错，跳过此视频。")

def day_to_chinese(day):
    days = ["日", "一", "二", "三", "四", "五", "六"]
    return days[day]

def main():
    while True:
        input_live_id = input("请输入 liveId：")
        if input_live_id.isdigit() and len(input_live_id) <= 10:
            break
        else:
            print("liveId 错误，请重新输入：")

    data = get_initial_data(input_live_id)

    if not data:
        print("没有找到数据，请检查 liveId 是否正确。")
        return

    first_entry = data[0]
    start_time = first_entry["startTime"]["time"]
    course_code = first_entry["courseCode"]
    course_name = first_entry["courseName"]

    start_time_unix = start_time / 1000
    start_time_struct = time.gmtime(start_time_unix)
    year = start_time_struct.tm_year

    save_dir = f"{year}年{course_code}{course_name}"
    os.makedirs(save_dir, exist_ok=True)

    csv_filename = os.path.join(save_dir, f"{save_dir}.csv")

    rows = []
    for entry in tqdm(data, desc="Processing entries"):
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

    for row in tqdm(rows, desc="Downloading videos"):
        month, date, day, jie, days, ppt_video, teacher_track = row
        day_chinese = day_to_chinese(day)

        if ppt_video:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo"
            download_m3u8(ppt_video, filename, save_dir)

        if teacher_track:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-teacherTrack"
            download_m3u8(teacher_track, filename, save_dir)

    print("所有视频下载完成。")

if __name__ == "__main__":
    main()
