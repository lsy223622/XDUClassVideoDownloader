#!/usr/bin/env python3

import requests
import urllib.parse
import json
from utils import handle_exception, remove_invalid_chars
import subprocess
import time
import random

VERSION = "2.9.0"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": "UID=2"
}

def get_initial_data(liveid):
    response = requests.post("http://newesxidian.chaoxing.com/live/listSignleCourse", headers=HEADERS, data={"liveId": liveid})
    response.raise_for_status()
    return response.json()

def get_m3u8_text(live_id, u = 0):
    time.sleep(random.randint(1, 50))
    if u > 10:
        return ''
    elif u != 0:
        print(f"{live_id}正在进行第{u + 1}/10次尝试")
    try:
    # if True:
        result_text = ''
        result = subprocess.run(
            ['curl', 
            f'http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId={live_id}',
            '--compressed',
            '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: en-US,en;q=0.5',
            '-H', 'Accept-Encoding: gzip, deflate',
            '-H', 'Connection: keep-alive', 
            '-H', 'Cookie: UID=2',
            '-H', 'Upgrade-Insecure-Requests: 1',
            '-H', 'Priority: u=0, i'],
            capture_output=True,
            text=True,
            check=True  # 如果 curl 返回非零状态码，会抛出异常
        )
        # return result.stdout
        result_text = result.stdout.strip()
        if result_text == '':
            result_text = get_m3u8_text(live_id, u + 1)
        return result_text
    except subprocess.CalledProcessError as e:
        print(e)
        return ''
        
def get_m3u8_links(live_id, u = 0):
    response_text = get_m3u8_text(live_id)
    if response_text.strip() == '':
        raise ValueError(f"在获取{live_id}时10次尝试失败，学校服务器杂鱼了")
    encoded_info = response_text.split('info=')[-1]
    decoded_info = urllib.parse.unquote(encoded_info)
    info_json = json.loads(decoded_info)

    video_paths = info_json.get('videoPath', {})
    if video_paths is None:
        raise ValueError("videoPath not found in the response")

    return video_paths.get('pptVideo', ''), video_paths.get('teacherTrack', '')


def fetch_data(url):
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        handle_exception(e, "请求错误")
        return None
    except ValueError as e:
        handle_exception(e, "解析 JSON 错误")
        return None

def scan_courses(user_id, term_year, term_id):
    week = 1
    consecutive_empty_weeks = 0
    first_classes = {}

    while consecutive_empty_weeks < 2:
        data = fetch_data(f"https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage?fid=16820&userId={user_id}&week={week}&termYear={term_year}&termId={term_id}")

        if data and len(data) > 0:
            for item in data:
                course_id = item['courseId']
                if course_id not in first_classes:
                    item['courseName'] = remove_invalid_chars(item['courseName'])
                    first_classes[course_id] = item
            consecutive_empty_weeks = 0
        else:
            consecutive_empty_weeks += 1

        week += 1

    return first_classes

def compare_versions(v1, v2):
    v1_parts = list(map(int, v1.split('.')))
    v2_parts = list(map(int, v2.split('.')))
    for i in range(3):
        if v1_parts[i] > v2_parts[i]:
            return 1
        elif v1_parts[i] < v2_parts[i]:
            return -1
    return 0

def check_update():
    print("正在检查更新...")
    try:
        response = requests.get(
            f"https://api.lsy223622.com/xcvd.php?version={VERSION}",
            timeout=10
        )
        data = response.json()
        if data.get("message"):
            print(data["message"])
        if data.get("latest_version"):
            latest_version = data["latest_version"]
            if compare_versions(latest_version, VERSION) > 0:
                print(f"有新版本可用: {latest_version}，请访问 https://github.com/lsy223622/XDUClassVideoDownloader/releases 下载。")
    except Exception as e:
        print(f"检查更新时发生错误: {e}")

def fetch_m3u8_links(entry, lock, desc):
    """
    获取单个课程条目的 m3u8 链接，并处理异常。
    """
    try:
        ppt_video, teacher_track = get_m3u8_links(entry["id"])
        start_time_struct = time.gmtime(entry["startTime"]["time"] / 1000)
        row = [
            start_time_struct.tm_mon, start_time_struct.tm_mday,
            entry["startTime"]["day"], entry["jie"], entry["days"],
            ppt_video, teacher_track
        ]
        with lock:
            desc.update(1)
        return row
    except ValueError as e:
        print(f"获取视频链接时发生错误：{e}，liveId: {entry['id']}")
        return None
