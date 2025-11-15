#!/usr/bin/env python3
"""
API 模块
负责与西安电子科技大学录直播平台服务器进行安全通信

主要功能：
- 安全的 HTTP 请求处理，包含重试机制和超时控制
- 课程数据获取和解析，包含数据验证
- 视频链接获取，支持多种视频格式
- 版本检查和更新通知
- 统一的错误处理和日志记录

安全特性：
- 输入验证和 URL 安全检查
- 请求频率限制和反爬虫保护
- 敏感信息过滤和安全日志记录
"""

import base64
import hashlib
import json
import random
import re
import time
import urllib.parse
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union, cast

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import format_auth_cookies, get_auth_cookies
from utils import remove_invalid_chars, setup_logging
from validator import is_valid_url, validate_live_id, validate_scan_parameters

# 配置日志（模块日志 + 总日志；控制台仅 error+）
logger = setup_logging("api")

# 应用版本和配置
VERSION = "3.3.1"
FID = "16820"

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


_Func = TypeVar("_Func", bound=Callable[..., Any])


class VideoGeneratingError(Exception):
    """Raised when the replay video is still being generated (页面提示: 视频回看生成中)."""

    pass


def aes_cbc_pkcs7_encrypt_base64(message: str, key_str: str) -> str:
    """使用 AES/CBC/PKCS7 对 message 加密并返回 Base64 字符串。

    设计目标是与 CryptoJS 中使用的 raw key + iv 行为兼容（内部按需派生固定长度 key/iv）。
    """
    raw_key = key_str.encode("utf-8")
    key = raw_key if len(raw_key) in (16, 24, 32) else hashlib.sha256(raw_key).digest()
    iv = key[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    ct = cipher.encrypt(pad(message.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("utf-8")


def get_three_cookies_from_login(
    username: str,
    password: str,
    base_url: str = "https://passport2.chaoxing.com",
    timeout: int = 10,
) -> Dict[str, Optional[str]]:
    """通过账号密码登录获取三个 Cookie 值。

    参数:
        username (str): 用户名
        password (str): 密码
        base_url (str): 登录基础 URL
        timeout (int): 请求超时时间

    返回:
        dict: 包含 _d, UID, vc3 的字典

    异常:
        RuntimeError: 登录失败时
    """
    session = requests.Session()

    login_url = base_url.rstrip("/") + "/login"
    logger.debug(f"GET {login_url}")
    resp = session.get(login_url, timeout=timeout)
    resp.raise_for_status()

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    def _hid(name):
        el = soup.find(id=name)
        return el.get("value") if el and el.has_attr("value") else ""

    t_flag = _hid("t")

    key_pattern = r"transferKey\s*[:=]\s*['\"]([^'\"]+)['\"]"
    match = re.search(key_pattern, html)
    if match:
        transfer_key = match.group(1)
        logger.debug("Found transferKey in page HTML")
    else:
        transfer_key = ""
        script_src = next(
            (sc["src"] for sc in soup.find_all("script", src=True) if "login" in sc["src"].lower()),
            None,
        )
        if script_src:
            js_url = urllib.parse.urljoin(login_url, script_src)
            try:
                jr = session.get(js_url, timeout=timeout)
                jr.raise_for_status()
                js_match = re.search(key_pattern, jr.text)
                transfer_key = js_match.group(1) if js_match else ""
            except Exception as e:
                logger.debug("Failed to fetch/parse JS %s: %s", js_url, e)

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
    logger.debug(f"POST {post_url} (encrypted={'true' if t_flag=='true' else 'false'})")
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


def rate_limit(func: _Func) -> _Func:
    """
    装饰器：为 API 请求添加频率限制，防止对服务器造成过大压力。
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
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

    return cast(_Func, wrapper)


def create_session() -> requests.Session:
    """
    创建配置了重试策略的 HTTP 会话。

    返回:
        requests.Session: 配置好的会话对象
    """
    session = requests.Session()

    # 配置重试策略
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def get_authenticated_headers() -> Dict[str, str]:
    """
    获取包含身份验证信息的 HTTP 请求头。

    返回:
        dict: 包含认证 cookie 和安全 headers 的请求头字典

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
            "Pragma": "no-cache",
        }

        return headers

    except Exception as e:
        logger.error(f"获取认证头失败: {e}")
        raise ValueError(f"无法获取有效的认证信息: {e}")


@rate_limit
def get_initial_data(liveid: Union[int, str]) -> List[Dict[str, Any]]:
    """
    根据课程 ID 获取课程的初始数据信息，包含完整的错误处理和数据验证。

    参数:
        liveid (int): 课程的直播 ID

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
        request_data = {"liveId": validated_liveid, "fid": FID}

        logger.info(f"正在获取课程 {validated_liveid} 的初始数据")

        # 发送 POST 请求
        logger.debug(f"POST http://newes.chaoxing.com/xidianpj/live/listSignleCourse with data={request_data}")
        response = session.post(
            "http://newes.chaoxing.com/xidianpj/live/listSignleCourse",
            headers=headers,
            data=request_data,
            timeout=REQUEST_TIMEOUT,
        )

        # 检查 HTTP 状态
        response.raise_for_status()

        # 解析 JSON 响应
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"响应 JSON 解析失败: {e}")
            raise ValueError("服务器响应格式错误，请稍后重试")

        # 验证响应数据结构
        if not isinstance(data, list):
            logger.warning(f"响应数据类型异常，期望列表但收到: {type(data)}")
            if isinstance(data, dict) and "error" in data:
                raise ValueError(f"服务器返回错误: {data.get('error', '未知错误')}")
            raise ValueError("服务器响应数据格式异常")

        if len(data) == 0:
            logger.warning(f"课程 {validated_liveid} 没有找到数据")
            return []

        # 验证数据完整性
        required_fields = ["id", "courseCode", "courseName", "startTime", "endTime"]
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                logger.warning(f"第 {i} 项数据格式错误，跳过")
                continue

            missing_fields = [field for field in required_fields if field not in item]
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
def get_video_info_from_html(live_id: Union[int, str], retry_count: int = 0) -> Dict[str, Any]:
    """
    从 API 获取视频信息，通过解析 HTML 页面中的 infostr 变量。
    增强了错误处理和重试机制。

    参数:
        live_id (int): 直播课程 ID
        retry_count (int): 当前重试次数

    返回:
        dict: 解析后的视频信息，包含 videoPath 等字段

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
        sleep_time = RETRY_BACKOFF_FACTOR * ((2**retry_count) + random.uniform(0, 1))
        time.sleep(sleep_time)

    try:
        # 构建 API URL
        url = f"http://newes.chaoxing.com/xidianpj/frontLive/playVideo2Keda?liveId={validated_live_id}"

        if not is_valid_url(url):
            raise ValueError(f"构建的 URL 无效: {url}")

        # 获取认证头和创建会话
        headers = get_authenticated_headers()
        session = create_session()

        logger.debug(f"正在获取视频信息: {validated_live_id}")

        # 发送 GET 请求获取 HTML 页面
        logger.debug(f"GET {url}")
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        html_content = response.text

        if not html_content:
            raise ValueError("服务器返回空响应")

        # 检测“视频回看生成中”提示页：无需继续解析，直接视为尚未结束/不可下载
        # 关键字可能包含：视频回看生成中，需要 1-3 天处理完成
        if "视频回看生成中" in html_content or "需要1-3天处理完成" in html_content:
            logger.info(f"liveId {validated_live_id} 回看仍在生成中，跳过此次解析")
            # 不进入重试逻辑，直接抛出特殊异常供上层跳过
            raise VideoGeneratingError(f"回看生成中: {validated_live_id}")

        # 从 HTML 中提取 infostr 变量，使用更严格的正则表达式
        # 查找: var infostr = "...";
        pattern = r'var\s+infostr\s*=\s*"([^"]+)"\s*;'
        match = re.search(pattern, html_content)

        if not match:
            # 如果找不到 infostr，尝试其他可能的模式
            alternative_patterns = [
                r'infostr\s*=\s*"([^"]+)"',
                r"var\s+infostr\s*=\s*\'([^\']+)\'",
            ]

            for alt_pattern in alternative_patterns:
                match = re.search(alt_pattern, html_content)
                if match:
                    break

            if not match:
                # 若不是“生成中”页面但缺少 infostr，保持原有重试策略
                if retry_count < MAX_RETRIES:
                    logger.warning(f"未找到 infostr 变量，重试中...")
                    return get_video_info_from_html(live_id, retry_count + 1)
                else:
                    logger.warning(f"无法在 HTML 响应中找到视频信息变量，liveId: {validated_live_id}")
                    raise ValueError(f"无法获取视频信息，课程 ID: {validated_live_id}")

        encoded_info = match.group(1)

        if not encoded_info:
            raise ValueError("提取的视频信息为空")

        # URL 解码
        try:
            decoded_info = urllib.parse.unquote(encoded_info)
        except Exception as e:
            raise ValueError(f"URL解码失败: {e}")

        # 解析 JSON 数据
        try:
            info_json = json.loads(decoded_info)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 原始数据长度: {len(decoded_info)}")
            raise ValueError(f"视频信息 JSON 解析失败: {e}")

        # 验证 JSON 结构
        if not isinstance(info_json, dict):
            raise ValueError("视频信息格式错误，期望字典类型")

        logger.info(f"成功获取视频信息: {validated_live_id}")
        return info_json

    except requests.Timeout:
        if retry_count < MAX_RETRIES:
            logger.warning(f"请求超时，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(f"请求超时，课程 ID: {validated_live_id}")

    except requests.ConnectionError:
        if retry_count < MAX_RETRIES:
            logger.warning(f"网络连接错误，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(f"网络连接失败，课程 ID: {validated_live_id}")

    except requests.HTTPError as e:
        error_msg = f"HTTP 错误 {e.response.status_code}, 课程 ID: {validated_live_id}"
        logger.error(error_msg)

        if e.response.status_code in [429, 503] and retry_count < MAX_RETRIES:
            logger.warning(f"服务器繁忙，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(error_msg)
    except VideoGeneratingError:
        # 直接向上抛出，不做重试也不包装
        raise
    except Exception as e:
        logger.warning(f"获取视频信息时发生未知错误: {e}")
        if retry_count < MAX_RETRIES:
            return get_video_info_from_html(live_id, retry_count + 1)
        else:
            raise ValueError(f"获取视频信息失败: {e}")


def get_mp4_links(live_id: Union[int, str]) -> Tuple[str, str]:
    """
    从直播 ID 获取 PPT 视频和教师视频的下载链接（增强版）。

    参数:
        live_id (int): 直播课程 ID

    返回:
        tuple: (ppt_video_url, teacher_track_url) 两个视频的 URL

    异常:
        ValueError: 当获取视频链接失败时
    """
    try:
        # 获取视频信息
        info_json = get_video_info_from_html(live_id)

        # 验证响应结构
        if "videoPath" not in info_json:
            logger.warning(f"响应中缺少 videoPath 字段，课程 ID: {live_id}")
            return "", ""

        video_paths = info_json["videoPath"]

        if video_paths is None:
            logger.warning(f"videoPath 为空，课程 ID: {live_id}")
            return "", ""

        if not isinstance(video_paths, dict):
            logger.warning(f"videoPath 格式错误，期望字典但收到: {type(video_paths)}")
            return "", ""

        # 提取视频URL并验证
        ppt_video = video_paths.get("pptVideo", "")
        teacher_track = video_paths.get("teacherTrack", "")

        # 验证 URL 格式（如果存在）
        if ppt_video and not is_valid_url(ppt_video):
            logger.warning(f"PPT 视频 URL 格式无效: {ppt_video}")
            ppt_video = ""

        if teacher_track and not is_valid_url(teacher_track):
            logger.warning(f"教师视频 URL 格式无效: {teacher_track}")
            teacher_track = ""

        if not ppt_video and not teacher_track:
            logger.warning(f"没有找到有效的视频链接，课程 ID: {live_id}")
        else:
            logger.info(
                f"成功获取视频链接，课程 ID: {live_id}, PPT: {'是' if ppt_video else '否'}, 教师: {'是' if teacher_track else '否'}"
            )

        return ppt_video, teacher_track

    except VideoGeneratingError as e:
        # 特殊情况：视频尚未生成，记录为 warning 并向上游表明应跳过
        logger.warning(str(e))
        raise
    except Exception as e:
        logger.error(f"获取视频链接失败，课程 ID: {live_id}, 错误: {e}")
        raise ValueError(f"获取视频链接失败: {str(e)}")


@rate_limit
def fetch_data(url: str) -> Optional[Any]:
    """
    向指定 URL 发送安全的 GET 请求并返回 JSON 数据，增强错误处理。

    参数:
        url (str): 要请求的 URL 地址

    返回:
        dict: 解析后的 JSON 数据，失败时返回 None

    异常:
        ValueError: 当 URL 格式无效时
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL 不能为空且必须是字符串类型")

    if not is_valid_url(url):
        raise ValueError(f"URL 格式无效: {url}")

    try:
        # 创建会话并发送GET请求
        headers = get_authenticated_headers()
        session = create_session()

        logger.debug(f"正在请求 URL: {url}")
        logger.debug(f"GET {url}")
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        # 解析JSON响应
        try:
            data = response.json()
            logger.debug(f"成功获取数据，数据类型: {type(data)}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None

    except requests.Timeout:
        logger.error(f"请求超时: {url}")
        return None
    except requests.ConnectionError:
        logger.error(f"网络连接失败: {url}")
        return None
    except requests.HTTPError as e:
        logger.error(f"HTTP 错误: {e.response.status_code}, URL: {url}")
        return None
    except Exception as e:
        logger.error(f"请求失败: {e}, URL: {url}")
        return None


def scan_courses(user_id: str, term_year: int, term_id: int) -> Dict[int, Dict[str, Any]]:
    """
    扫描指定用户在指定学期的所有课程信息，包含完整的错误处理和数据验证。

    参数:
        user_id (str): 用户 ID
        term_year (int): 学年
        term_id (int): 学期 ID (1或2)

    返回:
        dict: 以课程 ID 为键的课程信息字典

    异常:
        ValueError: 当参数无效时
    """
    # 验证输入参数
    validate_scan_parameters(user_id, term_year, term_id)

    logger.info(f"开始扫描课程 - 用户 ID: {user_id}, 学年: {term_year}, 学期: {term_id}")

    week = 1  # 从第 1 周开始扫描
    consecutive_empty_weeks = 0  # 连续空周计数器
    first_classes = {}  # 存储每门课程的第一次出现信息
    max_weeks = 20  # 设置最大扫描周数，避免无限循环

    # 当连续 2 周没有课程时停止扫描，或达到最大周数
    while consecutive_empty_weeks < 2 and week <= max_weeks:
        try:
            # 构建请求 URL，获取指定周的课程数据
            url = f"https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage?fid={FID}&userId={user_id}&week={week}&termYear={term_year}&termId={term_id}"
            data = fetch_data(url)

            if data and isinstance(data, list) and len(data) > 0:
                logger.debug(f"第 {week} 周找到 {len(data)} 门课程")
                # 遍历该周的所有课程
                for item in data:
                    if not isinstance(item, dict):
                        logger.warning(f"第 {week} 周课程数据格式错误，跳过")
                        continue

                    course_id = item.get("courseId")
                    if not course_id:
                        logger.warning(f"第 {week} 周课程缺少 courseId，跳过")
                        continue

                    # 只保存每门课程的第一次出现信息
                    if course_id not in first_classes:
                        try:
                            # 验证必要字段
                            required_fields = ["courseCode", "courseName", "id"]
                            for field in required_fields:
                                if field not in item:
                                    logger.warning(f"课程 {course_id} 缺少字段 {field}")

                            # 移除课程名称中的非法字符
                            if "courseName" in item:
                                item["courseName"] = remove_invalid_chars(item["courseName"])

                            first_classes[course_id] = item
                            logger.debug(f"添加新课程: {course_id} - {item.get('courseName', '未知')}")
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


def compare_versions(v1: str, v2: str) -> int:
    """
    比较两个版本号的大小，支持更灵活的版本号格式。

    参数:
        v1 (str): 第一个版本号（格式：x.y.z 或 x.y）
        v2 (str): 第二个版本号（格式：x.y.z 或 x.y）

    返回:
        int: 1 表示 v1 > v2，-1 表示 v1 < v2，0 表示 v1 == v2

    异常:
        ValueError: 当版本号格式无效时
    """

    def parse_version(version):
        """解析版本号字符串为整数列表"""
        if not version or not isinstance(version, str):
            raise ValueError(f"版本号必须是非空字符串: {version}")

        try:
            parts = [int(x) for x in version.split(".")]
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


def check_update() -> None:
    """
    检查软件是否有新版本可用，包含更好的错误处理和用户体验。
    """
    print("正在检查更新...", end="", flush=True)

    try:
        # 向API服务器请求最新版本信息
        session = create_session()
        url = f"https://api.lsy223622.com/xcvd.php?version={VERSION}"
        logger.debug(f"GET {url}")
        response = session.get(url, timeout=10)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.warning("版本检查响应不是有效的 JSON 格式")
            print("\r检查更新失败：服务器响应格式错误")
            return

        # 先检查是否有新版本并提示用户（优先级高）
        latest_version = data.get("latest_version")
        if latest_version:
            try:
                if compare_versions(latest_version, VERSION) > 0:
                    print(f"\r有新版本可用: {latest_version}")
                    print("请访问 https://github.com/lsy223622/XDUClassVideoDownloader/releases 下载")
                    logger.info(f"发现新版本: {latest_version}")
                else:
                    # 没有新版本，清除"正在检查更新..."文字
                    print("\r" + " " * 30 + "\r", end="", flush=True)
                    logger.debug("当前版本已是最新版本")
            except Exception as e:
                logger.warning(f"版本号比较失败: {e}")
                print("\r版本检查完成")
        else:
            # 未返回版本信息，清除提示占位
            print("\r" + " " * 30 + "\r", end="", flush=True)

        # 然后显示服务器返回的 message（如果有）
        if data.get("message"):
            # 将服务器消息放在单独一行，保留前面的版本提示
            print(f"\r{data['message']}")

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


def fetch_video_links(entry: Dict[str, Any], lock: Lock, desc: Any, api_version: str = "new") -> Optional[List[Any]]:
    """
    获取单个课程条目的视频链接（pptVideo / teacherTrack），用于多线程环境中安全地获取视频链接。
    包含完整的错误处理和数据验证。

    参数:
        entry (dict): 包含课程信息的字典
        lock (threading.Lock): 线程锁，用于安全更新进度条
        desc (tqdm): 进度条对象
        api_version (str): API 版本，"new"表示新版（mp4），"legacy"表示旧版（m3u8）

    返回:
        list: 包含视频信息的列表，格式为[月, 日, 星期, 节次, 周数, ppt_video_url, teacher_track_url]
        None: 获取失败时返回 None
    """
    if not isinstance(entry, dict):
        logger.error(f"课程条目数据格式错误，期望字典但收到: {type(entry)}")
        with lock:
            desc.update(1)
        return None

    required_fields = ["id", "startTime", "jie", "days"]
    for field in required_fields:
        if field not in entry:
            logger.error(f"课程条目缺少必要字段: {field}")
            with lock:
                desc.update(1)
            return None

    try:
        # 根据 API 版本获取视频链接
        if api_version == "legacy":
            # 旧版 API：获取 M3U8 链接
            ppt_video, teacher_track = get_m3u8_links_legacy(entry["id"])
        else:
            # 新版 API：获取 MP4 链接
            ppt_video, teacher_track = get_mp4_links(entry["id"])

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
            ppt_video,  # PPT 视频 URL
            teacher_track,  # 教师视频 URL
        ]

        # 使用线程锁安全地更新进度条
        with lock:
            desc.update(1)
        logger.debug(f"成功获取课程 {entry['id']} 的视频链接")
        return row

    except VideoGeneratingError:
        # 回看仍在生成中：不视为错误，按需求用 warning 级别以示区别
        with lock:
            desc.update(1)
        logger.warning(f"课程 {entry.get('id')} 回看仍在生成中，跳过")
        return None
    except Exception as e:
        # 记录获取视频链接失败的错误信息，使用 warning 级别避免打断进度条显示
        # exc_info=True 会记录完整 traceback 到日志文件
        live_id = entry.get("id", "未知")
        logger.warning(f"获取视频链接失败 (课程 ID: {live_id}): {type(e).__name__}: {e}", exc_info=True)

        with lock:
            desc.update(1)
        return None


def detect_api_version(data: List[Dict[str, Any]]) -> str:
    """
    检测课程数据使用的 API 版本。

    通过检查课程数据中的 termYear 字段判断应使用新版 API 还是旧版 API。
    2024 及以前的学年使用旧版 API（m3u8 格式），2025 及之后使用新版 API（mp4 格式）。

    参数:
        data (List[Dict[str, Any]]): 课程数据列表

    返回:
        str: "legacy"表示旧版 API（2024 及以前），"new"表示新版 API（2025 及之后）
    """
    if not data or len(data) == 0:
        logger.warning("课程数据为空，默认使用新版 API")
        return "new"

    # 从第一条数据中获取termYear
    term_year = data[0].get("termYear")

    if term_year is None:
        logger.warning("无法获取 termYear，默认使用新版 API")
        return "new"

    # 2024 及以前使用旧版 API，2025 及之后使用新版 API
    if term_year <= 2024:
        logger.info(f"检测到 termYear={term_year}，使用旧版 API（m3u8 格式）")
        return "legacy"
    else:
        logger.info(f"检测到 termYear={term_year}，使用新版 API（mp4 格式）")
        return "new"


@rate_limit
def get_m3u8_info_legacy(live_id: Union[int, str], retry_count: int = 0) -> Dict[str, Any]:
    """
    使用旧版 API 从服务器获取 M3U8 视频信息（2024 及以前的课程）。

    旧版 API 返回的是 HTML 页面，包含 URL 编码的 JSON 数据，指向 M3U8 播放列表。
    与 v2.9.0-beta 不同的是，现在需要携带 _d、UID、vc3 这三个 cookies。

    参数:
        live_id (Union[int, str]): 直播课程ID
        retry_count (int): 当前重试次数

    返回:
        Dict[str, Any]: 包含 videoPath 的字典，其中 pptVideo 和 teacherTrack 是 M3U8 链接

    异常:
        ValueError: 当获取视频信息失败时
    """
    # 验证输入参数
    validated_live_id = validate_live_id(live_id)

    # 检查重试次数
    if retry_count > MAX_RETRIES:
        raise ValueError(f"获取旧版视频信息失败，已达到最大重试次数 ({MAX_RETRIES})")

    if retry_count > 0:
        logger.info(f"正在进行第 {retry_count + 1}/{MAX_RETRIES + 1} 次尝试获取旧版视频信息")
        # 指数退避
        sleep_time = RETRY_BACKOFF_FACTOR * ((2**retry_count) + random.uniform(0, 1))
        time.sleep(sleep_time)

    try:
        # 构建旧版 API URL（注意是 /live/ 不是 /xidianpj/live/）
        url = f"http://newesxidian.chaoxing.com/live/getViewUrlHls?liveId={validated_live_id}"

        if not is_valid_url(url):
            raise ValueError(f"构建的 URL 无效: {url}")

        # 获取认证头和创建会话（关键：旧版 API 现在也需要 cookies）
        headers = get_authenticated_headers()
        session = create_session()

        logger.debug(f"正在获取旧版视频信息: {validated_live_id}")

        # 发送 GET 请求
        logger.debug(f"GET {url}")
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        html_content = response.text

        if not html_content:
            raise ValueError("服务器返回空响应")

        # 检测"视频回看生成中"提示页
        if "视频回看生成中" in html_content or "需要1-3天处理完成" in html_content:
            logger.info(f"liveId {validated_live_id} 回看仍在生成中，跳过此次解析")
            raise VideoGeneratingError(f"回看生成中: {validated_live_id}")

        # 旧版 API 返回的 HTML 中包含类似这样的内容：
        # ...info=%7B%22videoPath%22%3A%7B%22pptVideo%22%3A%22http%3A...
        # 提取 info 参数（URL 编码的 JSON 数据）
        if "info=" not in html_content:
            if retry_count < MAX_RETRIES:
                logger.warning(f"未找到 info 参数，重试中...")
                return get_m3u8_info_legacy(live_id, retry_count + 1)
            else:
                logger.warning(f"无法在响应中找到视频信息，liveId: {validated_live_id}")
                raise ValueError(f"无法获取旧版视频信息，课程 ID: {validated_live_id}")

        # 从响应中提取 info 参数
        encoded_info = html_content.split("info=")[-1]
        # 可能后面还有其他参数，取第一个&之前的内容
        if "&" in encoded_info:
            encoded_info = encoded_info.split("&")[0]
        # 也可能是在 HTML 标签中，取第一个<或"之前的内容
        for delimiter in ["<", '"', "'"]:
            if delimiter in encoded_info:
                encoded_info = encoded_info.split(delimiter)[0]

        if not encoded_info:
            raise ValueError("提取的视频信息为空")

        # URL 解码
        try:
            decoded_info = urllib.parse.unquote(encoded_info)
        except Exception as e:
            raise ValueError(f"URL 解码失败: {e}")

        # 解析 JSON 数据
        try:
            info_json = json.loads(decoded_info)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 原始数据长度: {len(decoded_info)}")
            raise ValueError(f"旧版视频信息 JSON 解析失败: {e}")

        # 验证 JSON 结构
        if not isinstance(info_json, dict):
            raise ValueError("旧版视频信息格式错误，期望字典类型")

        logger.info(f"成功获取旧版视频信息: {validated_live_id}")
        return info_json

    except requests.Timeout:
        if retry_count < MAX_RETRIES:
            logger.warning(f"请求超时，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_m3u8_info_legacy(live_id, retry_count + 1)
        else:
            raise ValueError(f"请求超时，课程 ID: {validated_live_id}")

    except requests.ConnectionError:
        if retry_count < MAX_RETRIES:
            logger.warning(f"网络连接错误，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_m3u8_info_legacy(live_id, retry_count + 1)
        else:
            raise ValueError(f"网络连接失败，课程 ID: {validated_live_id}")

    except requests.HTTPError as e:
        error_msg = f"HTTP 错误 {e.response.status_code}, 课程 ID: {validated_live_id}"
        logger.error(error_msg)

        if e.response.status_code in [429, 503] and retry_count < MAX_RETRIES:
            logger.warning(f"服务器繁忙，正在重试... ({retry_count + 1}/{MAX_RETRIES + 1})")
            return get_m3u8_info_legacy(live_id, retry_count + 1)
        else:
            raise ValueError(error_msg)
    except VideoGeneratingError:
        # 直接向上抛出，不做重试也不包装
        raise
    except Exception as e:
        logger.warning(f"获取旧版视频信息时发生未知错误: {e}")
        if retry_count < MAX_RETRIES:
            return get_m3u8_info_legacy(live_id, retry_count + 1)
        else:
            raise ValueError(f"获取旧版视频信息失败: {e}")


def get_m3u8_links_legacy(live_id: Union[int, str]) -> Tuple[str, str]:
    """
    从直播 ID 获取 PPT 视频和教师视频的 M3U8 链接（旧版 API，2024 及以前）。

    参数:
        live_id (Union[int, str]): 直播课程 ID

    返回:
        Tuple[str, str]: (ppt_video_m3u8_url, teacher_track_m3u8_url) 两个 M3U8 链接

    异常:
        ValueError: 当获取视频链接失败时
    """
    try:
        # 获取视频信息
        info_json = get_m3u8_info_legacy(live_id)

        # 验证响应结构
        if "videoPath" not in info_json:
            logger.warning(f"响应中缺少 videoPath 字段，课程 ID: {live_id}")
            return "", ""

        video_paths = info_json["videoPath"]

        if video_paths is None:
            logger.warning(f"videoPath 为空，课程 ID: {live_id}")
            return "", ""

        if not isinstance(video_paths, dict):
            logger.warning(f"videoPath 格式错误，期望字典但收到: {type(video_paths)}")
            return "", ""

        # 提取 M3U8 URL 并验证
        ppt_video = video_paths.get("pptVideo", "")
        teacher_track = video_paths.get("teacherTrack", "")

        # 验证 URL 格式（如果存在）
        if ppt_video and not is_valid_url(ppt_video):
            logger.warning(f"PPT 视频 M3U8 链接格式无效: {ppt_video}")
            ppt_video = ""

        if teacher_track and not is_valid_url(teacher_track):
            logger.warning(f"教师视频 M3U8 链接格式无效: {teacher_track}")
            teacher_track = ""

        if not ppt_video and not teacher_track:
            logger.warning(f"没有找到有效的 M3U8 链接，课程 ID: {live_id}")
        else:
            logger.info(
                f"成功获取 M3U8 链接，课程 ID: {live_id}, PPT: {'是' if ppt_video else '否'}, 教师: {'是' if teacher_track else '否'}"
            )

        return ppt_video, teacher_track

    except VideoGeneratingError as e:
        # 特殊情况：视频尚未生成
        logger.warning(str(e))
        raise
    except Exception as e:
        # 使用 warning 级别，避免在获取链接时打断进度条显示
        logger.warning(f"获取 M3U8 链接失败，课程 ID: {live_id}, 错误: {e}")
        raise ValueError(f"获取 M3U8 链接失败: {str(e)}")
