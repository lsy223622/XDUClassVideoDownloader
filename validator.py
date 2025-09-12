#!/usr/bin/env python3
"""
验证模块
专门负责各种数据验证和输入检查

主要功能：
- 参数验证
- 输入格式检查
- 数据完整性验证
- URL和文件名验证
"""

import re
import os
import logging
from datetime import datetime
from utils import setup_logging

# 配置日志
logger = setup_logging('validator', level=logging.INFO,
                       console_level=logging.ERROR)


def validate_live_id(live_id):
    """
    验证直播ID的格式和有效性。

    参数:
        live_id: 待验证的直播ID

    返回:
        int: 验证后的直播ID

    异常:
        ValueError: 当直播ID格式无效时
    """
    if live_id is None:
        raise ValueError("直播ID不能为空")

    try:
        live_id_int = int(live_id)
        if live_id_int <= 0:
            raise ValueError("直播ID必须是正整数")
        if live_id_int > 9999999999:  # 设置合理的上限
            raise ValueError("直播ID超出有效范围")
        return live_id_int
    except (TypeError, ValueError) as e:
        raise ValueError(f"直播ID格式无效: {live_id}")


def validate_user_id(user_id):
    """
    验证用户ID的有效性。

    参数:
        user_id (str): 用户ID

    返回:
        bool: 是否有效
    """
    if not user_id or not isinstance(user_id, str):
        return False

    # 用户ID应该是数字字符串，长度在6-20之间
    user_id = user_id.strip()
    if not user_id.isdigit():
        return False

    if len(user_id) < 6 or len(user_id) > 20:
        return False

    return True


def validate_term_params(year, term_id):
    """
    验证学期参数的有效性。

    参数:
        year (int): 学年
        term_id (int): 学期ID

    返回:
        bool: 是否有效
    """
    try:
        year = int(year)
        term_id = int(term_id)

        # 学年应该在合理范围内
        current_year = datetime.now().year
        if year < 2000 or year > current_year + 1:
            return False

        # 学期ID应该是1或2
        if term_id not in [1, 2]:
            return False

        return True
    except (ValueError, TypeError):
        return False


def validate_download_parameters(liveid, single, video_type):
    """
    验证下载参数的有效性。

    参数:
        liveid: 课程直播ID
        single (int): 下载模式
        video_type (str): 视频类型

    返回:
        tuple: (validated_liveid, validated_single, validated_video_type)

    异常:
        ValueError: 当参数无效时
    """
    # 验证liveid
    if liveid is not None:
        validated_liveid = validate_live_id(liveid)
    else:
        validated_liveid = None

    # 验证single模式
    if not isinstance(single, int) or single < 0 or single > 2:
        raise ValueError("下载模式必须是0（全部）、1（单节课）或2（半节课）")

    # 验证video_type
    if video_type not in ['both', 'ppt', 'teacher']:
        raise ValueError("视频类型必须是 'both', 'ppt' 或 'teacher'")

    return validated_liveid, single, video_type


def validate_input(value, validator, error_message="输入格式错误"):
    """
    验证用户输入的通用函数。

    参数:
        value: 待验证的值
        validator: 验证函数或正则表达式
        error_message (str): 验证失败时的错误消息

    返回:
        bool: 验证是否通过

    异常:
        ValueError: 当验证器类型不正确时
    """
    try:
        if callable(validator):
            return validator(value)
        elif isinstance(validator, str):
            # 作为正则表达式处理
            return bool(re.match(validator, str(value)))
        else:
            raise ValueError("验证器必须是函数或正则表达式字符串")
    except Exception as e:
        logger.warning(f"输入验证失败: {e}")
        return False


def is_valid_url(url):
    """
    验证URL格式是否有效。

    参数:
        url (str): 待验证的URL

    返回:
        bool: URL是否有效
    """
    if not url or not isinstance(url, str):
        return False

    # 基本的URL格式验证
    url_pattern = re.compile(
        r'^https?://'  # http:// 或 https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP地址
        r'(?::\d+)?'  # 可选端口
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return bool(url_pattern.match(url))


def validate_file_integrity(filepath, expected_size=None):
    """
    验证下载文件的完整性。

    参数:
        filepath (str): 文件路径
        expected_size (int): 期望的文件大小（可选）

    返回:
        bool: 文件是否完整有效
    """
    try:
        if not os.path.exists(filepath):
            return False

        file_size = os.path.getsize(filepath)
        MIN_FILE_SIZE = 1024  # 最小有效文件大小（字节）

        # 检查文件大小是否合理
        if file_size < MIN_FILE_SIZE:
            logger.warning(f"文件大小过小，可能下载不完整: {filepath} ({file_size} bytes)")
            return False

        # 如果提供了期望大小，进行比较
        if expected_size is not None and abs(file_size - expected_size) > 1024:
            logger.warning(f"文件大小不匹配，期望: {expected_size}, 实际: {file_size}")
            return False

        # 简单的文件头验证（MP4文件应该以特定字节开头）
        try:
            with open(filepath, 'rb') as f:
                header = f.read(8)
                # MP4文件头通常包含 'ftyp' 标识
                if len(header) >= 8 and b'ftyp' in header:
                    logger.debug(f"文件头验证通过: {filepath}")
                    return True
                else:
                    logger.warning(f"文件头验证失败，可能不是有效的MP4文件: {filepath}")
                    return False
        except Exception as e:
            logger.warning(f"文件头验证时出错: {e}")
            return False

    except Exception as e:
        logger.error(f"文件完整性验证失败: {e}")
        return False


def validate_scan_parameters(user_id, term_year, term_id):
    """
    验证课程扫描参数的有效性。

    参数:
        user_id (str): 用户ID
        term_year (int): 学年
        term_id (int): 学期ID

    异常:
        ValueError: 当参数无效时
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("用户ID不能为空且必须是字符串类型")

    if not str(user_id).isdigit():
        raise ValueError("用户ID必须是数字")

    try:
        term_year = int(term_year)
        if term_year < 2020 or term_year > 2030:
            raise ValueError("学年必须在2020-2030范围内")
    except (TypeError, ValueError):
        raise ValueError("学年必须是有效的整数")

    try:
        term_id = int(term_id)
        if term_id not in [1, 2]:
            raise ValueError("学期ID必须是1或2")
    except (TypeError, ValueError):
        raise ValueError("学期ID必须是1或2")


def validate_course_data(entry):
    """
    验证课程数据的完整性。

    参数:
        entry (dict): 课程数据条目

    返回:
        bool: 数据是否有效
    """
    if not isinstance(entry, dict):
        logger.warning(f"课程数据格式错误，期望字典但收到: {type(entry)}")
        return False

    required_fields = ['id', 'courseCode',
                       'courseName', 'startTime', 'endTime']
    missing_fields = [field for field in required_fields if field not in entry]

    if missing_fields:
        logger.warning(f"课程数据缺少字段: {missing_fields}")
        return False

    return True


def validate_video_info(video_info):
    """
    验证视频信息的完整性。

    参数:
        video_info (dict): 视频信息

    返回:
        bool: 信息是否有效
    """
    if not isinstance(video_info, dict):
        return False

    if 'videoPath' not in video_info:
        return False

    video_paths = video_info['videoPath']
    if video_paths is None or not isinstance(video_paths, dict):
        return False

    # 至少应该有一种视频类型
    ppt_video = video_paths.get('pptVideo', '')
    teacher_track = video_paths.get('teacherTrack', '')

    return bool(ppt_video or teacher_track)


def validate_cookie_value(value):
    """
    验证Cookie值的格式。

    参数:
        value (str): Cookie值

    返回:
        bool: 是否有效
    """
    return bool(value and len(value.strip()) > 0 and not any(char in value for char in ['\n', '\r', '\t']))


def validate_filename_components(row):
    """
    验证从行数据中提取的文件名组件。

    参数:
        row (list): 视频信息行

    返回:
        tuple: (month, date, day, jie, days) 或 None（如果验证失败）
    """
    try:
        if not isinstance(row, list) or len(row) < 7:
            logger.warning(f"行数据格式错误: {row}")
            return None

        month, date, day, jie, days = row[:5]

        # 类型转换和验证
        try:
            month = int(month)
            date = int(date)
            jie = int(jie)
            if not (1 <= month <= 12):
                raise ValueError(f"月份无效: {month}")
            if not (1 <= date <= 31):
                raise ValueError(f"日期无效: {date}")
            if jie < 1:
                raise ValueError(f"节次无效: {jie}")
        except (TypeError, ValueError) as e:
            logger.warning(f"时间数据格式错误: {e}")
            return None

        return month, date, day, jie, days

    except Exception as e:
        logger.warning(f"解析行数据时出错: {e}")
        return None
