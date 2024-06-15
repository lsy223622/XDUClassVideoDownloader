import requests
import json
import csv
import urllib.parse
import os
import subprocess
from tqdm import tqdm

def get_initial_data():
    url = "http://newesxidian.chaoxing.com/live/listSignleCourse"
    headers = {
        "User-Agent": "Mozilla/5.0 (Wayland; Linux x86_64; rv:120.1) Gecko/20100101 Firefox/120.1",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.7,ja;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://newesxidian.chaoxing.com",
        "DNT": "1",
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Referer": "http://newesxidian.chaoxing.com/live/viewNewCourseLive1?isStudent=1",
        "Cookie": "UID=9876"
    }
    data = {
        "liveId": "11740668"
    }

    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()

def get_m3u8_links(live_id):
    url = f"http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId={live_id}&status=2&jie=&isStudent="
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.7,ja;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "X-Requested-With": "XMLHttpRequest",
        "DNT": "1",
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Referer": "http://newesxidian.chaoxing.com/live/viewNewCourseLive1?isStudent=1",
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
    student_full = video_paths.get('studentFull', '')

    return ppt_video, teacher_track, student_full

def download_m3u8(url, filename):
    command = f'N_m3u8DL-RE.exe "{url}" --save-dir "m3u8" --save-name "{filename}"'
    subprocess.run(command, shell=True, check=True)

def main():
    data = get_initial_data()

    rows = []
    for entry in tqdm(data, desc="Processing entries"):
        live_id = entry["id"]
        month = entry["startTime"]["month"]
        date = entry["startTime"]["date"]
        day = entry["startTime"]["day"]
        jie = entry["jie"]
        days = entry["days"]

        ppt_video, teacher_track, student_full = get_m3u8_links(live_id)

        row = [month, date, day, jie, days, ppt_video, teacher_track, student_full]
        rows.append(row)

    with open('m3u8.csv', mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['month', 'date', 'day', 'jie', 'days', 'pptVideo', 'teacherTrack', 'studentFull'])
        writer.writerows(rows)

    print("m3u8.csv 文件已创建并写入数据。")

    for row in tqdm(rows, desc="Downloading videos"):
        month, date, day, jie, days, ppt_video, teacher_track, student_full = row

        if ppt_video:
            filename = f"{month + 1}月{date}日第{days}周星期{day}-pptVideo"
            download_m3u8(ppt_video, filename)

        if teacher_track:
            filename = f"{month + 1}月{date}日第{days}周星期{day}-teacherTrack"
            download_m3u8(teacher_track, filename)

        if student_full:
            filename = f"{month + 1}月{date}日第{days}周星期{day}-studentFull"
            download_m3u8(student_full, filename)

    print("所有视频下载完成。")

if __name__ == "__main__":
    main()
