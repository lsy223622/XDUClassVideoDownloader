#!/usr/bin/env python3

import requests
import urllib.parse
import json

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
