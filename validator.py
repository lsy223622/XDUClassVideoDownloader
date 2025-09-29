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

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Union

from utils import setup_logging

# 配置日志（模块日志 + 总日志；控制台仅 error+）
logger = setup_logging("validator")


def validate_live_id(live_id: Union[int, str]) -> int:
    """
    验证直播ID的格式和有效性。

    参数:
        live_id (Union[int, str]): 待验证的直播 ID。

    返回:
        int: 验证后的直播 ID。

    异常:
        ValueError: 当直播 ID 格式无效时。
    """
    if live_id is None:
        raise ValueError("直播 ID 不能为空")

    try:
        live_id_int = int(live_id)
        if live_id_int <= 0:
            raise ValueError("直播 ID 必须是正整数")
        if live_id_int > 9999999999:  # 设置合理的上限
            raise ValueError("直播 ID 超出有效范围")
        return live_id_int
    except (TypeError, ValueError) as e:
        raise ValueError(f"直播 ID 格式无效: {live_id}") from e


def validate_user_id(user_id: str) -> bool:
    """
    验证用户ID的有效性。

    参数:
        user_id (str): 用户 ID。

    返回:
        bool: 是否有效。
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


def validate_term_params(year: Union[int, str], term_id: Union[int, str]) -> bool:
    """
    验证学期参数的有效性。

    参数:
        year (Union[int, str]): 学年。
        term_id (Union[int, str]): 学期 ID。

    返回:
        bool: 是否有效。
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


def validate_download_parameters(
    liveid: Optional[Union[int, str]], single: int, video_type: str
) -> Tuple[Optional[int], int, str]:
    """
    验证下载参数的有效性。

    参数:
        liveid (Optional[Union[int, str]]): 课程直播 ID。
        single (int): 下载模式。
        video_type (str): 视频类型。

    返回:
        tuple: (validated_liveid, validated_single, validated_video_type)。

    异常:
        ValueError: 当参数无效时。
    """
    # 验证liveid
    if liveid is not None:
        validated_liveid = validate_live_id(liveid)
    else:
        validated_liveid = None

    # 验证single模式
    if not isinstance(single, int) or single < 0 or single > 2:
        raise ValueError("下载模式必须是 0（全部）、1（单节课）或 2（半节课）")

    # 验证video_type
    if video_type not in ["both", "ppt", "teacher"]:
        raise ValueError('视频类型必须是 "both"、"ppt" 或 "teacher"')

    return validated_liveid, single, video_type


def validate_input(
    value: Any, validator: Union[Callable[[Any], bool], str], error_message: str = "输入格式错误"
) -> bool:
    """
    验证用户输入的通用函数。

    参数:
        value (Any): 待验证的值。
        validator (Union[Callable[[Any], bool], str]): 验证函数或正则表达式。
        error_message (str): 验证失败时的错误消息。

    返回:
        bool: 验证是否通过。

    异常:
        ValueError: 当验证器类型不正确时。
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


def is_valid_url(url: str) -> bool:
    """
    验证URL格式是否有效。

    参数:
        url (str): 待验证的 URL。

    返回:
        bool: URL 是否有效。
    """
    if not url or not isinstance(url, str):
        return False

    # 基本的URL格式验证
    url_pattern = re.compile(
        r"^https?://"  # http:// 或 https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # 域名
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP 地址
        r"(?::\d+)?"  # 可选端口
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    return bool(url_pattern.match(url))


def validate_file_integrity(filepath: str, expected_size: Optional[int] = None) -> bool:
    """
    验证下载文件的完整性。

    参数:
        filepath (str): 文件路径。
        expected_size (Optional[int]): 期望的文件大小（可选）。

    返回:
        bool: 文件是否完整有效。
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
            with open(filepath, "rb") as f:
                header = f.read(8)
                # MP4文件头通常包含 'ftyp' 标识
                if len(header) >= 8 and b"ftyp" in header:
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


def validate_scan_parameters(user_id: str, term_year: Union[int, str], term_id: Union[int, str]) -> None:
    """
    验证课程扫描参数的有效性。

    参数:
        user_id (str): 用户 ID。
        term_year (Union[int, str]): 学年。
        term_id (Union[int, str]): 学期 ID。

    异常:
        ValueError: 当参数无效时。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("用户 ID 不能为空且必须是字符串类型")

    if not str(user_id).isdigit():
        raise ValueError("用户 ID 必须是数字")

    try:
        term_year = int(term_year)
        if term_year < 2020 or term_year > 2030:
            raise ValueError("学年必须在 2020-2030 范围内")
    except (TypeError, ValueError):
        raise ValueError("学年必须是有效的整数")

    try:
        term_id = int(term_id)
        if term_id not in [1, 2]:
            raise ValueError("学期 ID 必须是 1 或 2")
    except (TypeError, ValueError):
        raise ValueError("学期 ID 必须是 1 或 2")


def validate_course_data(entry: Dict[str, Any]) -> bool:
    """
    验证课程数据的完整性。

    参数:
        entry (Dict[str, Any]): 课程数据条目。

    返回:
        bool: 数据是否有效。
    """
    if not isinstance(entry, dict):
        logger.warning(f"课程数据格式错误，期望字典但收到: {type(entry)}")
        return False

    required_fields = ["id", "courseCode", "courseName", "startTime", "endTime"]
    missing_fields = [field for field in required_fields if field not in entry]

    if missing_fields:
        logger.warning(f"课程数据缺少字段: {missing_fields}")
        return False

    return True


def validate_video_info(video_info: Dict[str, Any]) -> bool:
    """
    验证视频信息的完整性。

    参数:
        video_info (Dict[str, Any]): 视频信息。

    返回:
        bool: 信息是否有效。
    """
    if not isinstance(video_info, dict):
        return False

    if "videoPath" not in video_info:
        return False

    video_paths = video_info["videoPath"]
    if video_paths is None or not isinstance(video_paths, dict):
        return False

    # 至少应该有一种视频类型
    ppt_video = video_paths.get("pptVideo", "")
    teacher_track = video_paths.get("teacherTrack", "")

    return bool(ppt_video or teacher_track)

