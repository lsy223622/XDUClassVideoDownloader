#!/usr/bin/env python3
"""
API模块
负责与西安电子科技大学录直播平台服务器进行安全通信

主要功能：
- 安全的HTTP请求处理，包含重试机制和超时控制
- 课程数据获取和解析，包含数据验证
- 视频链接获取，支持多种视频格式
- 版本检查和更新通知
- 统一的错误处理和日志记录

安全特性：
- 输入验证和URL安全检查
- 请求频率限制和反爬虫保护
- 敏感信息过滤和安全日志记录
"""

import requests
import urllib.parse
import json
import re
import time
import random
import logging
import base64
import hashlib
from functools import wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from utils import remove_invalid_chars, setup_logging
from config import get_auth_cookies, format_auth_cookies
from validator import is_valid_url, validate_live_id, validate_scan_parameters

# 配置日志
logger = setup_logging('api', level=logging.INFO,
                       console_level=logging.WARNING)

# 应用版本和配置
VERSION = "3.0.0"  # 更新版本号以反映改进
FID = '16820'

# 请求配置
REQUEST_TIMEOUT = 30  # 请求超时时间（秒）
MAX_RETRIES = 3  # 最大重试次数
RETRY_BACKOFF_FACTOR = 0.3  # 重试退避因子
MAX_REDIRECT = 5  # 最大重定向次数

# 频率限制配置
REQUEST_DELAY_MIN = 1  # 最小请求间隔（秒）
REQUEST_DELAY_MAX = 3  # 最大请求间隔（秒）

# 上次请求时间，用于频率控制
_last_request_time = 0


def _derive_aes_key_iv(key_str):
    """将任意长度的字符串派生为 AES key/iv。

    - 如果原始字节长度为 16/24/32，直接使用；否则使用 SHA-256 摘要（32 字节）兼容任意输入。
    - IV 固定为 key 的前 16 字节（与常见 CryptoJS 用法一致）。
    """
    raw = key_str.encode("utf-8")
    if len(raw) in (16, 24, 32):
        key = raw
    else:
        key = hashlib.sha256(raw).digest()
    iv = key[:16]
    return key, iv


def aes_cbc_pkcs7_encrypt_base64(message, key_str):
    """使用 AES/CBC/PKCS7 对 message 加密并返回 Base64 字符串。

    设计目标是与 CryptoJS 中使用的 raw key + iv 行为兼容（当前脚本通过 _derive_aes_key_iv 保证 key/iv 长度）。
    """
    key, iv = _derive_aes_key_iv(key_str)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    ct = cipher.encrypt(pad(message.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("utf-8")


def _extract_transfer_key_from_text(text):
    """从传入文本中查找 transferKey 的简单正则表达式匹配。

    返回匹配到的字符串或者 None。
    """
    m = re.search(r"transferKey\s*[:=]\s*['\"]([^'\"]+)['\"]", text)
    return m.group(1) if m else None


def _find_transfer_key(session, login_url, html, timeout):
    """先在 HTML 中查找 transferKey，找不到时尝试寻找包含 'login' 的外部 script 并请求以提取 key。

    如果最终仍未找到，返回空字符串（调用方可使用默认 key）。
    """
    key = _extract_transfer_key_from_text(html)
    if key:
        logger.debug("Found transferKey in page HTML")
        return key

    soup = BeautifulSoup(html, "html.parser")
    # 优先寻找 name 或 src 中包含 login 的 script
    script_src = None
    for sc in soup.find_all("script", src=True):
        src = sc["src"]
        if "login" in src.lower():
            script_src = src
            break

    if not script_src:
        return ""

    js_url = urllib.parse.urljoin(login_url, script_src)
    try:
        jr = session.get(js_url, timeout=timeout)
        jr.raise_for_status()
        return _extract_transfer_key_from_text(jr.text) or ""
    except Exception as e:
        logger.debug("Failed to fetch/parse JS %s: %s", js_url, e)
        return ""


def get_three_cookies_from_login(username, password, base_url="https://passport2.chaoxing.com", timeout=10):
    """通过账号密码登录获取三个Cookie值。

    参数:
        username (str): 用户名
        password (str): 密码
        base_url (str): 登录基础URL
        timeout (int): 请求超时时间

    返回:
        dict: 包含 _d, UID, vc3 的字典

    异常:
        RuntimeError: 登录失败时
    """
    session = requests.Session()

    login_url = base_url.rstrip("/") + "/login"
    resp = session.get(login_url, timeout=timeout)
    resp.raise_for_status()

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    def _hid(name):
        el = soup.find(id=name)
        return el.get("value") if el and el.has_attr("value") else ""

    t_flag = _hid("t")

    transfer_key = _find_transfer_key(session, login_url, html, timeout)
    if not transfer_key:
        # 历史默认值，保留以兼容未提供 transferKey 的情况
        transfer_key = "u2oh6Vu^HWe4_AES"
        logger.debug("Using fallback transfer_key")

    # 根据页面 t 值决定是否对用户名/密码进行加密
    uname_payload = username
    pwd_payload = password
    if t_flag == "true":
        uname_payload = aes_cbc_pkcs7_encrypt_base64(username, transfer_key)
        pwd_payload = aes_cbc_pkcs7_encrypt_base64(password, transfer_key)

    post_url = base_url.rstrip("/") + "/fanyalogin"
    data = {
        "fid": _hid("fid") or "-1",
        "uname": uname_payload,
        "password": pwd_payload,
        "refer": _hid("refer") or "",
        "t": t_flag,
        "forbidotherlogin": _hid("forbidotherlogin") or "0",
        "validate": _hid("validate") or "",
        "doubleFactorLogin": _hid("doubleFactorLogin") or "0",
        "independentId": _hid("independentId") or "0",
        "independentNameId": _hid("independentNameId") or "0",
    }

    headers = {"User-Agent": "python-requests/2.x", "Referer": login_url}

    r = session.post(post_url, data=data, headers=headers, timeout=timeout)
    try:
        j = r.json()
    except Exception as e:
        raise RuntimeError("登录请求未返回 JSON: %s" % e)

    if not j.get("status"):
        raise RuntimeError(j.get("msg2") or j.get("mes") or "登录失败")

    # 从会话中提取 cookie，返回指定的三项（若不存在则为 None）
    cookie_jar = requests.utils.dict_from_cookiejar(session.cookies)
    return {"_d": cookie_jar.get("_d"), "UID": cookie_jar.get("UID"), "vc3": cookie_jar.get("vc3")}


def rate_limit(func):
    """
    装饰器：为API请求添加频率限制，防止对服务器造成过大压力。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        global _last_request_time
        current_time = time.time()

        # 计算需要等待的时间
        time_since_last = current_time - _last_request_time
        min_interval = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)

        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            logger.debug(f"频率限制: 等待 {sleep_time:.2f} 秒")
            time.sleep(sleep_time)

        _last_request_time = time.time()
        return func(*args, **kwargs)

    return wrapper


def create_session():
    """
    创建配置了重试策略的HTTP会话。

    返回:
        requests.Session: 配置好的会话对象
    """
    session = requests.Session()

    # 配置重试策略
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def get_authenticated_headers():
    """
    获取包含身份验证信息的HTTP请求头。

    返回:
        dict: 包含认证cookie和安全headers的请求头字典

    异常:
        ValueError: 当认证信息无效时
    """
    try:
        auth_cookies = get_auth_cookies(FID)
        cookie_string = format_auth_cookies(auth_cookies)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cookie": cookie_string,
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }

        return headers

    except Exception as e:
        logger.error(f"获取认证头失败: {e}")
        raise ValueError(f"无法获取有效的认证信息: {e}")


@rate_limit
def get_initial_data(liveid):
    """
    根据课程ID获取课程的初始数据信息，包含完整的错误处理和数据验证。

    参数:
        liveid (int): 课程的直播ID

    返回:
        list: 包含课程信息的列表

    异常:
        ValueError: 当参数无效或响应数据无效时
        requests.RequestException: 当网络请求失败时
    """
    # 验证输入参数
    validated_liveid = validate_live_id(liveid)

    try:
        # 获取认证头和创建会话
        headers = get_authenticated_headers()
        session = create_session()

        # 构建请求数据
        request_data = {
            "liveId": validated_liveid,
            "fid": FID
        }

        logger.info(f"正在获取课程 {validated_liveid} 的初始数据")

        # 发送POST请求
        response = session.post(
            "http://newes.chaoxing.com/xidianpj/live/listSignleCourse",
            headers=headers,
            data=request_data,
            timeout=REQUEST_TIMEOUT
        )

        # 检查HTTP状态
        response.raise_for_status()

        # 解析JSON响应
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"响应JSON解析失败: {e}")
            raise ValueError("服务器响应格式错误，请稍后重试")

        # 验证响应数据结构
        if not isinstance(data, list):
            logger.warning(f"响应数据类型异常，期望列表但收到: {type(data)}")
            if isinstance(data, dict) and 'error' in data:
                raise ValueError(f"服务器返回错误: {data.get('error', '未知错误')}")
            raise ValueError("服务器响应数据格式异常")

        if len(data) == 0:
            logger.warning(f"课程 {validated_liveid} 没有找到数据")
            return []

        # 验证数据完整性
        required_fields = ['id', 'courseCode',
                           'courseName', 'startTime', 'endTime']
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                logger.warning(f"第 {i} 项数据格式错误，跳过")
                continue

            missing_fields = [
                field for field in required_fields if field not in item]
            if missing_fields:
                logger.warning(f"第 {i} 项数据缺少字段: {missing_fields}")

        logger.info(f"成功获取课程数据，共 {len(data)} 项")
        return data

    except requests.Timeout:
        error_msg = "请求超时，请检查网络连接"
        logger.error(error_msg)
        raise requests.RequestException(error_msg)

    except requests.ConnectionError:
        error_msg = "网络连接失败，请检查网络设置"
        logger.error(error_msg)
        raise requests.RequestException(error_msg)

    except requests.HTTPError as e:
        error_msg = f"服务器响应错误: HTTP {e.response.status_code}"
        logger.error(error_msg)
        raise requests.RequestException(error_msg)

    except Exception as e:
        logger.error(f"获取初始数据时发生未知错误: {e}")
        raise


@rate_limit
def get_video_info_from_html(live_id, retry_count=0):
    """
    从API获取视频信息，通过解析HTML页面中的infostr变量。
    增强了错误处理和重试机制。

    参数:
        live_id (int): 直播课程ID
        retry_count (int): 当前重试次数

    返回:
        dict: 解析后的视频信息，包含videoPath等字段

    异常:
        ValueError: 当获取视频信息失败或解析响应失败时抛出
    """
    # 验证输入参数
    validated_live_id = validate_live_id(live_id)

    # 检查重试次数
    if retry_count > MAX_RETRIES:
        raise ValueError(f"获取视频信息失败，已达到最大重试次数 ({MAX_RETRIES})")

    if retry_count > 0:
        logger.info(f"正在进行第 {retry_count + 1}/{MAX_RETRIES + 1} 次尝试获取视频信息")
        # 指数退避
        sleep_time = RETRY_BACKOFF_FACTOR * \
            (2 ** retry_count) + random.uniform(0, 1)
        time.sleep(sleep_time)

    try:
        # 构建API URL
        url = f"http://newes.chaoxing.com/xidianpj/frontLive/playVideo2Keda?liveId={validated_live_id}"

        if not is_valid_url(url):
            raise ValueError(f"构建的URL无效: {url}")

        # 获取认证头和创建会话
        headers = get_authenticated_headers()
        session = create_session()

        logger.debug(f"正在获取视频信息: {validated_live_id}")

        # 发送GET请求获取HTML页面
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        html_content = response.text

        if not html_content:
            raise ValueError("服务器返回空响应")

        # 从HTML中提取infostr变量，使用更严格的正则表达式
        # 查找: var infostr = "...";
        pattern = r'var\s+infostr\s*=\s*"([^"]+)"\s*;'
        match = re.search(pattern, html_content)

        if not match:
            # 如果找不到infostr，尝试其他可能的模式
            alternative_patterns = [
                r'infostr\s*=\s*"([^"]+)"',
                r'var\s+infostr\s*=\s*\'([^\']+)\'',
            ]

            for alt_pattern in alternative_patterns:
                match = re.search(alt_pattern, html_content)
                if match:
                    break

            if not match:
                if retry_count < MAX_RETRIES:
                    logger.warning(f"未找到infostr变量，重试中...")
                    return get_video_info_from_html(live_id, retry_count + 1)
                else:
                    logger.error(
                        f"无法在HTML响应中找到视频信息变量，liveId: {validated_live_id}")
                    raise ValueError(f"无法获取视频信息，课程ID: {validated_live_id}")

        encoded_info = match.group(1)

        if not encoded_info:
            raise ValueError("提取的视频信息为空")

        # URL解码
        try:
            decoded_info = urllib.parse.unquote(encoded_info)
        except Exception as e:
            raise ValueError(f"URL解码失败: {e}")

        # 解析JSON数据
        try:
            info_json = json.loads(decoded_info)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 原始数据长度: {len(decoded_info)}")
            raise ValueError(f"视频信息JSON解析失败: {e}")

        # 验证JSON结构
        if not isinstance(info_json, dict):
            raise ValueError("视频信息格式错误，期望字典类型")

        logger.info(f"成功获取视频信息: {validated_live_id}")
        return info_json

    except requests.Timeout:
        if retry_count < MAX_RETRIES:
            logger.warning(
                f"请求超时，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(f"请求超时，课程ID: {validated_live_id}")

    except requests.ConnectionError:
        if retry_count < MAX_RETRIES:
            logger.warning(
                f"网络连接错误，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(f"网络连接失败，课程ID: {validated_live_id}")

    except requests.HTTPError as e:
        error_msg = f"HTTP错误 {e.response.status_code}, 课程ID: {validated_live_id}"
        logger.error(error_msg)

        if e.response.status_code in [429, 503] and retry_count < MAX_RETRIES:
            logger.warning(
                f"服务器繁忙，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(error_msg)

    except Exception as e:
        logger.error(f"获取视频信息时发生未知错误: {e}")
        if retry_count < MAX_RETRIES:
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(f"获取视频信息失败: {e}")


def get_m3u8_links(live_id):
    """
    从直播ID获取PPT视频和教师视频的下载链接（增强版）。

    参数:
        live_id (int): 直播课程ID

    返回:
        tuple: (ppt_video_url, teacher_track_url) 两个视频的URL

    异常:
        ValueError: 当获取视频链接失败时
    """
    try:
        # 获取视频信息
        info_json = get_video_info_from_html(live_id)

        # 验证响应结构
        if 'videoPath' not in info_json:
            logger.warning(f"响应中缺少videoPath字段，课程ID: {live_id}")
            return '', ''

        video_paths = info_json['videoPath']

        if video_paths is None:
            logger.warning(f"videoPath为空，课程ID: {live_id}")
            return '', ''

        if not isinstance(video_paths, dict):
            logger.warning(f"videoPath格式错误，期望字典但收到: {type(video_paths)}")
            return '', ''

        # 提取视频URL并验证
        ppt_video = video_paths.get('pptVideo', '')
        teacher_track = video_paths.get('teacherTrack', '')

        # 验证URL格式（如果存在）
        if ppt_video and not is_valid_url(ppt_video):
            logger.warning(f"PPT视频URL格式无效: {ppt_video}")
            ppt_video = ''

        if teacher_track and not is_valid_url(teacher_track):
            logger.warning(f"教师视频URL格式无效: {teacher_track}")
            teacher_track = ''

        if not ppt_video and not teacher_track:
            logger.warning(f"没有找到有效的视频链接，课程ID: {live_id}")
        else:
            logger.info(
                f"成功获取视频链接，课程ID: {live_id}, PPT: {'是' if ppt_video else '否'}, 教师: {'是' if teacher_track else '否'}")

        return ppt_video, teacher_track

    except Exception as e:
        logger.error(f"获取视频链接失败，课程ID: {live_id}, 错误: {e}")
        raise ValueError(f"获取视频链接失败: {str(e)}")


# 保留旧函数但标记为废弃
def get_m3u8_text(live_id, u=0):
    """
    废弃的函数：获取M3U8播放列表的原始文本内容。

    注意：此函数已废弃，新版本使用get_video_info_from_html。
    """
    logger.warning("get_m3u8_text函数已废弃，请使用新的API函数")
    return ''


@rate_limit
def fetch_data(url):
    """
    向指定URL发送安全的GET请求并返回JSON数据，增强错误处理。

    参数:
        url (str): 要请求的URL地址

    返回:
        dict: 解析后的JSON数据，失败时返回None

    异常:
        ValueError: 当URL格式无效时
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL不能为空且必须是字符串类型")

    if not is_valid_url(url):
        raise ValueError(f"URL格式无效: {url}")

    try:
        # 创建会话并发送GET请求
        headers = get_authenticated_headers()
        session = create_session()

        logger.debug(f"正在请求URL: {url}")

        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        # 解析JSON响应
        try:
            data = response.json()
            logger.debug(f"成功获取数据，数据类型: {type(data)}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return None

    except requests.Timeout:
        logger.error(f"请求超时: {url}")
        return None
    except requests.ConnectionError:
        logger.error(f"网络连接失败: {url}")
        return None
    except requests.HTTPError as e:
        logger.error(f"HTTP错误: {e.response.status_code}, URL: {url}")
        return None
    except Exception as e:
        logger.error(f"请求失败: {e}, URL: {url}")
        return None


def scan_courses(user_id, term_year, term_id):
    """
    扫描指定用户在指定学期的所有课程信息，包含完整的错误处理和数据验证。

    参数:
        user_id (str): 用户ID
        term_year (int): 学年
        term_id (int): 学期ID (1或2)

    返回:
        dict: 以课程ID为键的课程信息字典

    异常:
        ValueError: 当参数无效时
    """
    # 验证输入参数
    validate_scan_parameters(user_id, term_year, term_id)

    logger.info(f"开始扫描课程 - 用户ID: {user_id}, 学年: {term_year}, 学期: {term_id}")

    week = 1  # 从第1周开始扫描
    consecutive_empty_weeks = 0  # 连续空周计数器
    first_classes = {}  # 存储每门课程的第一次出现信息
    max_weeks = 20  # 设置最大扫描周数，避免无限循环

    # 当连续2周没有课程时停止扫描，或达到最大周数
    while consecutive_empty_weeks < 2 and week <= max_weeks:
        try:
            # 构建请求URL，获取指定周的课程数据
            url = f"https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage?fid={FID}&userId={user_id}&week={week}&termYear={term_year}&termId={term_id}"
            data = fetch_data(url)

            if data and isinstance(data, list) and len(data) > 0:
                logger.debug(f"第 {week} 周找到 {len(data)} 门课程")
                # 遍历该周的所有课程
                for item in data:
                    if not isinstance(item, dict):
                        logger.warning(f"第 {week} 周课程数据格式错误，跳过")
                        continue

                    course_id = item.get('courseId')
                    if not course_id:
                        logger.warning(f"第 {week} 周课程缺少courseId，跳过")
                        continue

                    # 只保存每门课程的第一次出现信息
                    if course_id not in first_classes:
                        try:
                            # 验证必要字段
                            required_fields = [
                                'courseCode', 'courseName', 'id']
                            for field in required_fields:
                                if field not in item:
                                    logger.warning(
                                        f"课程 {course_id} 缺少字段 {field}")

                            # 移除课程名称中的非法字符
                            if 'courseName' in item:
                                item['courseName'] = remove_invalid_chars(
                                    item['courseName'])

                            first_classes[course_id] = item
                            logger.debug(
                                f"添加新课程: {course_id} - {item.get('courseName', '未知')}")
                        except Exception as e:
                            logger.warning(f"处理课程 {course_id} 时出错: {e}")
                            continue

                # 重置连续空周计数器
                consecutive_empty_weeks = 0
            else:
                # 该周没有课程，增加连续空周计数
                consecutive_empty_weeks += 1
                logger.debug(f"第 {week} 周没有课程数据")

        except Exception as e:
            logger.error(f"扫描第 {week} 周时出错: {e}")
            consecutive_empty_weeks += 1

        week += 1  # 检查下一周

    logger.info(f"课程扫描完成，共找到 {len(first_classes)} 门课程")
    return first_classes


def compare_versions(v1, v2):
    """
    比较两个版本号的大小，支持更灵活的版本号格式。

    参数:
        v1 (str): 第一个版本号（格式：x.y.z 或 x.y）
        v2 (str): 第二个版本号（格式：x.y.z 或 x.y）

    返回:
        int: 1表示v1>v2，-1表示v1<v2，0表示v1==v2

    异常:
        ValueError: 当版本号格式无效时
    """
    def parse_version(version):
        """解析版本号字符串为整数列表"""
        if not version or not isinstance(version, str):
            raise ValueError(f"版本号必须是非空字符串: {version}")

        try:
            parts = [int(x) for x in version.split('.')]
            # 确保至少有3个部分（主版本、次版本、修订版本）
            while len(parts) < 3:
                parts.append(0)
            return parts
        except ValueError:
            raise ValueError(f"版本号格式无效: {version}")

    try:
        v1_parts = parse_version(v1)
        v2_parts = parse_version(v2)

        # 逐个比较版本号的各个部分
        for i in range(min(len(v1_parts), len(v2_parts))):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1

        # 如果长度不同，长版本号更大
        if len(v1_parts) > len(v2_parts):
            return 1
        elif len(v1_parts) < len(v2_parts):
            return -1

        return 0

    except Exception as e:
        logger.error(f"版本号比较失败: {e}")
        return 0  # 比较失败时认为相等


def check_update():
    """
    检查软件是否有新版本可用，包含更好的错误处理和用户体验。
    """
    print("正在检查更新...", end="", flush=True)

    try:
        # 向API服务器请求最新版本信息
        session = create_session()
        response = session.get(
            f"https://api.lsy223622.com/xcvd.php?version={VERSION}",
            timeout=10
        )
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.warning("版本检查响应不是有效的JSON格式")
            print("\r检查更新失败：服务器响应格式错误")
            return

        # 显示服务器返回的消息
        if data.get("message"):
            print(f"\r{data['message']}")
        else:
            # 检查是否有新版本
            latest_version = data.get("latest_version")
            if latest_version:
                try:
                    # 比较版本号，如果有新版本则提示用户
                    if compare_versions(latest_version, VERSION) > 0:
                        print(f"\r有新版本可用: {latest_version}")
                        print(
                            "请访问 https://github.com/lsy223622/XDUClassVideoDownloader/releases 下载")
                        logger.info(f"发现新版本: {latest_version}")
                    else:
                        # 没有新版本，清除"正在检查更新..."文字
                        print("\r" + " " * 30 + "\r", end="", flush=True)
                        logger.debug("当前版本已是最新版本")
                except Exception as e:
                    logger.warning(f"版本号比较失败: {e}")
                    print("\r版本检查完成")
            else:
                # 清除"正在检查更新..."文字
                print("\r" + " " * 30 + "\r", end="", flush=True)

    except requests.Timeout:
        print("\r检查更新超时，跳过版本检查")
        logger.warning("版本检查超时")
    except requests.RequestException as e:
        print(f"\r检查更新失败：网络错误")
        logger.warning(f"版本检查网络错误: {e}")
    except Exception as e:
        # 检查更新失败时不影响主功能
        print(f"\r检查更新时发生错误")
        logger.warning(f"版本检查失败: {e}")


def fetch_m3u8_links(entry, lock, desc):
    """
    获取单个课程条目的视频链接，用于多线程环境中安全地获取视频链接。
    包含完整的错误处理和数据验证。

    参数:
        entry (dict): 包含课程信息的字典
        lock (threading.Lock): 线程锁，用于安全更新进度条
        desc (tqdm): 进度条对象

    返回:
        list: 包含视频信息的列表，格式为[月, 日, 星期, 节次, 周数, ppt_video_url, teacher_track_url]
        None: 获取失败时返回None
    """
    if not isinstance(entry, dict):
        logger.error(f"课程条目数据格式错误，期望字典但收到: {type(entry)}")
        with lock:
            desc.update(1)
        return None

    required_fields = ['id', 'startTime', 'jie', 'days']
    for field in required_fields:
        if field not in entry:
            logger.error(f"课程条目缺少必要字段: {field}")
            with lock:
                desc.update(1)
            return None

    try:
        # 获取PPT视频和教师视频的链接
        ppt_video, teacher_track = get_m3u8_links(entry["id"])

        # 验证和解析开始时间
        start_time = entry["startTime"]
        if not isinstance(start_time, dict) or "time" not in start_time:
            logger.error(f"开始时间格式错误: {start_time}")
            with lock:
                desc.update(1)
            return None

        try:
            start_time_struct = time.gmtime(start_time["time"] / 1000)
        except (TypeError, ValueError, OSError) as e:
            logger.error(f"时间戳解析失败: {e}")
            with lock:
                desc.update(1)
            return None

        # 构建返回的行数据
        row = [
            start_time_struct.tm_mon,  # 月份
            start_time_struct.tm_mday,  # 日期
            start_time.get("day", 0),  # 星期
            entry.get("jie", ""),  # 节次
            entry.get("days", ""),  # 周数
            ppt_video,  # PPT视频URL
            teacher_track  # 教师视频URL
        ]

        # 使用线程锁安全地更新进度条
        with lock:
            desc.update(1)

        logger.debug(f"成功获取课程 {entry['id']} 的视频链接")
        return row

    except Exception as e:
        # 记录获取视频链接失败的错误信息
        error_msg = f"获取视频链接时发生错误：{e}，liveId: {entry.get('id', '未知')}"
        logger.error(error_msg)
        print(error_msg)

        with lock:
            desc.update(1)
        return None
