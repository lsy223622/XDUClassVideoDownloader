#!/usr/bin/env python3

import requests
import urllib.parse
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": "UID=2"
}

def get_initial_data(liveid):
    url = "http://newesxidian.chaoxing.com/live/listSignleCourse"
    headers = HEADERS
    data = {
        "liveId": liveid
    }

    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()

def get_m3u8_links(live_id):
    url = f"http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId={live_id}&status=2"
    headers = HEADERS

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
    if video_paths is None:
        raise ValueError("videoPath not found in the response")

    ppt_video = video_paths.get('pptVideo', '')
    teacher_track = video_paths.get('teacherTrack', '')

    return ppt_video, teacher_track

def fetch_data(url, headers):
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
        return None
    except ValueError as e:
        print(f"解析 JSON 错误：{e}")
        return None

def scan_courses(user_id, year, term_id, headers):
    week = 1
    consecutive_empty_weeks = 0
    first_classes = {}

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

    return first_classes
