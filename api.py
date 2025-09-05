#!/usr/bin/env python3
"""
API模块
负责与西安电子科技大学录直播平台服务器进行通信
包括获取课程数据、视频链接、版本检查等功能
"""

import requests
import urllib.parse
import json
import re
from utils import handle_exception, remove_invalid_chars, get_auth_cookies, format_auth_cookies
import time
import random

VERSION = "2.9.0"

FID = '16820'

def get_authenticated_headers():
    """
    获取包含身份验证信息的HTTP请求头。
    
    返回:
        dict: 包含认证cookie的请求头字典
    """
    auth_cookies = get_auth_cookies(FID)
    cookie_string = format_auth_cookies(auth_cookies)
    
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cookie": cookie_string,
        "Upgrade-Insecure-Requests": "1"
    }

def get_initial_data(liveid):
    """
    根据课程ID获取课程的初始数据信息。
    
    参数:
        liveid (int): 课程的直播ID
        
    返回:
        dict: 包含课程信息的JSON数据
        
    异常:
        requests.HTTPError: 当HTTP请求失败时抛出
    """
    # 向学校服务器发送POST请求获取课程信息
    headers = get_authenticated_headers()
    response = requests.post("http://newes.chaoxing.com/xidianpj/live/listSignleCourse",
                             headers=headers,
                             data={"liveId": liveid, "fid": FID})
    # 检查HTTP响应状态，如果失败会抛出异常
    response.raise_for_status()
    return response.json()

def get_video_info_from_html(live_id, u=0):
    """
    从新的API获取视频信息，通过解析HTML页面中的infostr变量。
    
    参数:
        live_id (int): 直播课程ID
        u (int): 重试次数，默认为0
        
    返回:
        dict: 解析后的视频信息，包含videoPath等字段
        
    异常:
        ValueError: 当获取视频信息失败或解析响应失败时抛出
    """
    # 随机延迟1-10秒，避免对服务器造成过大压力
    time.sleep(random.randint(1, 10))
    
    # 超过10次重试则放弃
    if u > 10:
        raise ValueError(f"在获取{live_id}时10次尝试失败，学校服务器杂鱼了")
    elif u != 0:
        print(f"{live_id}正在进行第{u + 1}/10次尝试")
    
    try:
        # 构建新的API URL
        url = f"http://newes.chaoxing.com/xidianpj/frontLive/playVideo2Keda?liveId={live_id}"
        headers = get_authenticated_headers()
        
        # 发送GET请求获取HTML页面
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html_content = response.text
        
        # 从HTML中提取infostr变量
        # 查找: var infostr = "...";
        match = re.search(r'var infostr = "([^"]+)";', html_content)
        if not match:
            # 如果找不到infostr，可能需要重试
            if u < 10:
                return get_video_info_from_html(live_id, u + 1)
            else:
                raise ValueError(f"无法在HTML响应中找到infostr变量，liveId: {live_id}")
        
        encoded_info = match.group(1)
        
        # URL解码
        decoded_info = urllib.parse.unquote(encoded_info)
        
        # 解析JSON数据
        info_json = json.loads(decoded_info)
        
        return info_json
        
    except requests.RequestException as e:
        print(f"网络请求错误: {e}")
        if u < 10:
            return get_video_info_from_html(live_id, u + 1)
        else:
            raise ValueError(f"网络请求失败，liveId: {live_id}")
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        if u < 10:
            return get_video_info_from_html(live_id, u + 1)
        else:
            raise ValueError(f"JSON解析失败，liveId: {live_id}")

def get_m3u8_links(live_id, u=0):
    """
    从直播ID获取PPT视频和教师视频的下载链接（新版API）。
    
    参数:
        live_id (int): 直播课程ID
        u (int): 重试次数，默认为0
        
    返回:
        tuple: (ppt_video_url, teacher_track_url) 两个视频的URL
        
    异常:
        ValueError: 当获取视频链接失败或解析响应失败时抛出
    """
    try:
        # 获取视频信息
        info_json = get_video_info_from_html(live_id)
        
        # 提取视频路径信息
        video_paths = info_json.get('videoPath', {})
        if video_paths is None:
            raise ValueError("videoPath not found in the response")

        # 返回PPT视频和教师视频的URL，如果不存在则返回空字符串
        ppt_video = video_paths.get('pptVideo', '')
        teacher_track = video_paths.get('teacherTrack', '')
        
        return ppt_video, teacher_track
        
    except Exception as e:
        # 如果发生任何错误，记录并重新抛出
        raise ValueError(f"获取视频链接失败: {str(e)}")

# 保留旧的函数名但标记为废弃，以备兼容性
def get_m3u8_text(live_id, u=0):
    """
    废弃的函数：获取M3U8播放列表的原始文本内容。
    
    注意：此函数已废弃，新版本使用get_video_info_from_html。
    """
    print("警告：get_m3u8_text函数已废弃，请使用新的API函数。")
    return ''


def fetch_data(url):
    """
    向指定URL发送GET请求并返回JSON数据。
    
    参数:
        url (str): 要请求的URL地址
        
    返回:
        dict: 解析后的JSON数据，失败时返回None
    """
    try:
        # 发送GET请求，使用认证头
        headers = get_authenticated_headers()
        response = requests.get(url, headers=headers)
        # 检查响应状态
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        # 处理网络请求异常
        handle_exception(e, "请求错误")
        return None
    except ValueError as e:
        # 处理JSON解析异常
        handle_exception(e, "解析 JSON 错误")
        return None

def scan_courses(user_id, term_year, term_id):
    """
    扫描指定用户在指定学期的所有课程信息。
    
    参数:
        user_id (str): 用户ID
        term_year (int): 学年
        term_id (int): 学期ID (1或2)
        
    返回:
        dict: 以课程ID为键的课程信息字典
    """
    week = 1  # 从第1周开始扫描
    consecutive_empty_weeks = 0  # 连续空周计数器
    first_classes = {}  # 存储每门课程的第一次出现信息

    # 当连续2周没有课程时停止扫描
    while consecutive_empty_weeks < 2:
        # 构建请求URL，获取指定周的课程数据
        data = fetch_data(f"https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage?fid={FID}&userId={user_id}&week={week}&termYear={term_year}&termId={term_id}")

        if data and len(data) > 0:
            # 遍历该周的所有课程
            for item in data:
                course_id = item['courseId']
                # 只保存每门课程的第一次出现信息
                if course_id not in first_classes:
                    # 移除课程名称中的非法字符
                    item['courseName'] = remove_invalid_chars(item['courseName'])
                    first_classes[course_id] = item
            # 重置连续空周计数器
            consecutive_empty_weeks = 0
        else:
            # 该周没有课程，增加连续空周计数
            consecutive_empty_weeks += 1

        week += 1  # 检查下一周

    return first_classes

def compare_versions(v1, v2):
    """
    比较两个版本号的大小。
    
    参数:
        v1 (str): 第一个版本号（格式：x.y.z）
        v2 (str): 第二个版本号（格式：x.y.z）
        
    返回:
        int: 1表示v1>v2，-1表示v1<v2，0表示v1==v2
    """
    # 将版本号按点分割并转换为整数列表
    v1_parts = list(map(int, v1.split('.')))
    v2_parts = list(map(int, v2.split('.')))
    
    # 逐个比较版本号的各个部分
    for i in range(3):
        if v1_parts[i] > v2_parts[i]:
            return 1
        elif v1_parts[i] < v2_parts[i]:
            return -1
    return 0

def check_update():
    """
    检查软件是否有新版本可用。
    """
    print("正在检查更新...", end="", flush=True)
    try:
        # 向API服务器请求最新版本信息
        response = requests.get(
            f"https://api.lsy223622.com/xcvd.php?version={VERSION}",
            timeout=10
        )
        data = response.json()
        
        # 显示服务器返回的消息
        if data.get("message"):
            print(f"\r{data['message']}")
        else:
            # 检查是否有新版本
            if data.get("latest_version"):
                latest_version = data["latest_version"]
                # 比较版本号，如果有新版本则提示用户
                if compare_versions(latest_version, VERSION) > 0:
                    print(f"\r有新版本可用: {latest_version}，请访问 https://github.com/lsy223622/XDUClassVideoDownloader/releases 下载。")
                else:
                    # 没有新版本，清除"正在检查更新..."文字
                    print("\r" + " " * 20 + "\r", end="", flush=True)
            else:
                # 清除"正在检查更新..."文字
                print("\r" + " " * 20 + "\r", end="", flush=True)
    except Exception as e:
        # 检查更新失败时不影响主功能
        print(f"\r检查更新时发生错误: {e}")

def fetch_m3u8_links(entry, lock, desc):
    """
    获取单个课程条目的 m3u8 链接，并处理异常。
    用于多线程环境中安全地获取视频链接。
    
    参数:
        entry (dict): 包含课程信息的字典
        lock (threading.Lock): 线程锁，用于安全更新进度条
        desc (tqdm): 进度条对象
        
    返回:
        list: 包含视频信息的列表，格式为[月, 日, 星期, 节次, 周数, ppt_video_url, teacher_track_url]
        None: 获取失败时返回None
    """
    try:
        # 获取PPT视频和教师视频的M3U8链接
        ppt_video, teacher_track = get_m3u8_links(entry["id"])
        
        # 解析开始时间戳为时间结构
        start_time_struct = time.gmtime(entry["startTime"]["time"] / 1000)
        
        # 构建返回的行数据
        row = [
            start_time_struct.tm_mon, start_time_struct.tm_mday,  # 月份和日期
            entry["startTime"]["day"], entry["jie"], entry["days"],  # 星期、节次、周数
            ppt_video, teacher_track  # 两个视频流的URL
        ]
        
        # 使用线程锁安全地更新进度条
        with lock:
            desc.update(1)
        return row
    except ValueError as e:
        # 记录获取视频链接失败的错误信息
        print(f"获取视频链接时发生错误：{e}，liveId: {entry['id']}")
        return None
