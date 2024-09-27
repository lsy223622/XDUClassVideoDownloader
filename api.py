#!/usr/bin/env python3

import requests
import urllib.parse
import json
from utils import handle_exception

VERSION = "2.2.0"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": "UID=2"
}

def get_initial_data(liveid):
    response = requests.post("http://newesxidian.chaoxing.com/live/listSignleCourse", headers=HEADERS, data={"liveId": liveid})
    response.raise_for_status()
    return response.json()

def get_m3u8_links(live_id):
    response = requests.get(f"http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId={live_id}&status=2", headers=HEADERS)
    response.raise_for_status()
    response_text = response.text

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
    try:
        response = requests.get(f"https://api.lsy223622.com/xcvd.php?version={VERSION}")
        data = response.json()
        if data.get("message"):
            print(data["message"])
        if data.get("latest_version"):
            latest_version = data["latest_version"]
            if compare_versions(latest_version, VERSION) > 0:
                print(f"有新版本可用: {latest_version}，请访问 https://github.com/lsy223622/XDUClassVideoDownloader/releases 下载。")
    except Exception as e:
        print(f"检查更新时发生错误: {e}")
