#!/usr/bin/env python3
"""
工具模块
提供各种辅助函数，包括文件处理、系统资源监控等功能

主要功能：
- 文件系统操作和路径处理
- 用户输入验证和交互
- 系统资源监控
- 统一的异常处理和日志记录
- 字符串处理和格式化
"""

import os
import sys
import psutil
import stat
from pathlib import Path
import logging
import math


# 配置基础日志记录 - 只保存到文件
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'xdu_downloader.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def setup_logging(name='xdu_downloader', level=logging.INFO, console_level=logging.ERROR):
    """
    设置日志记录系统。

    详细日志保存到文件中，用户界面只显示警告和错误信息。

    参数:
        name (str): 日志记录器名称
        level: 文件日志级别
        console_level: 控制台日志级别（默认只显示WARNING及以上）

    返回:
        logging.Logger: 配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 创建日志目录
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    # 创建文件处理器 - 记录所有日志信息
    file_handler = logging.FileHandler(
        log_dir / f'{name}.log', encoding='utf-8')
    file_handler.setLevel(level)

    # 创建控制台处理器 - 默认只显示 ERROR 和 CRITICAL
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)

    # 创建详细的文件格式化器
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 创建简洁的控制台格式化器
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    # 设置格式化器
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)

    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def remove_invalid_chars(course_name):
    """
    移除文件名中的非法字符，确保可以在文件系统中创建文件。

    使用更安全和全面的字符过滤方法，同时保持文件名的可读性。

    参数:
        course_name (str): 原始课程名称

    返回:
        str: 移除非法字符后的课程名称

    异常:
        ValueError: 当输入为空或处理后名称为空时
    """
    if not course_name or not isinstance(course_name, str):
        raise ValueError("课程名称不能为空且必须是字符串类型")

    # 定义 Windows/Linux 文件系统中不允许的字符
    # 包括控制字符和保留字符
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\0']

    # 移除控制字符 (ASCII 0-31)
    cleaned_name = ''.join(char for char in course_name if ord(char) >= 32)

    # 替换非法字符为下划线，保持可读性
    for char in invalid_chars:
        cleaned_name = cleaned_name.replace(char, '_')

    # 移除首尾空白字符和点号（Windows不允许）
    cleaned_name = cleaned_name.strip(' .')

    # 检查 Windows 保留文件名
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + \
        [f'COM{i}' for i in range(1, 10)] + \
        [f'LPT{i}' for i in range(1, 10)]

    if cleaned_name.upper() in reserved_names:
        cleaned_name = f"_{cleaned_name}"

    # 限制文件名长度，避免路径过长问题
    if len(cleaned_name) > 100:
        cleaned_name = cleaned_name[:100].rstrip()

    if not cleaned_name:
        raise ValueError("处理后的课程名称为空，请检查原始名称")

    return cleaned_name


def day_to_chinese(day):
    """
    将星期数字转换为中文表示。

    参数:
        day (int): 星期数字 (0-6, 0代表星期日，或1-7，1代表星期一)

    返回:
        str: 对应的中文星期表示

    异常:
        ValueError: 当输入不是有效的星期数字时
    """
    if not isinstance(day, int):
        try:
            day = int(day)
        except (TypeError, ValueError):
            raise ValueError(f"星期数字必须是整数，收到：{type(day).__name__}")

    # 星期数字到中文的映射字典 - 支持两种格式
    if day == 0:
        return "日"  # 0代表星期日
    elif 1 <= day <= 7:
        days = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}
        return days[day]
    else:
        raise ValueError(f"星期数字必须在0-7范围内，收到：{day}")


def user_input_with_check(prompt, validator, max_attempts=3, error_message="输入格式错误，请重新输入", allow_empty=False):
    """
    带验证功能的用户输入函数，提供更好的用户体验和安全性。

    参数:
        prompt (str): 提示信息
        validator: 验证函数或正则表达式
        max_attempts (int): 最大尝试次数
        error_message (str): 验证失败时的错误消息

    返回:
        str: 验证通过的用户输入

    异常:
        ValueError: 超过最大尝试次数时
    """
    from validator import validate_input

    attempts = 0
    while attempts < max_attempts:
        try:
            user_input = input(prompt).strip()

            # 如果允许空输入且用户直接回车，则返回空字符串
            if allow_empty and user_input == '':
                return user_input

            if validate_input(user_input, validator):
                return user_input
            else:
                print(error_message)
                attempts += 1
        except KeyboardInterrupt:
            print("\n用户中断操作")
            raise
        except EOFError:
            print("\n输入流结束")
            raise ValueError("输入流意外结束")

    raise ValueError(f"超过最大尝试次数 ({max_attempts})，输入验证失败")


def create_directory(directory):
    """
    安全地创建目录，包含权限设置和原子性保证。

    参数:
        directory (str): 要创建的目录路径

    异常:
        OSError: 创建目录失败时
        ValueError: 路径参数无效时
    """
    if not directory or not isinstance(directory, str):
        raise ValueError("目录路径不能为空且必须是字符串类型")

    try:
        # 使用 Path 对象处理路径，更安全
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)

        # 设置适当的权限 (仅在Unix系统上有效)
        if os.name == 'posix':
            try:
                os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
            except OSError:
                logger.warning(f"无法设置目录权限: {directory}")

        logger.info(f"目录创建成功: {directory}")

    except OSError as e:
        logger.error(f"创建目录失败: {directory}, 错误: {e}")
        raise OSError(f"无法创建目录 {directory}: {e}")


def handle_exception(e, message, level=logging.ERROR):
    """
    统一的异常处理函数，提供更安全的错误信息记录。

    参数:
        e (Exception): 异常对象
        message (str): 自定义错误消息
        level: 日志级别

    返回:
        str: 用户友好的错误消息
    """
    # 生成用户友好的错误消息
    if isinstance(e, (ConnectionError, OSError)):
        user_message = f"{message}：网络连接或文件操作失败"
    elif isinstance(e, ValueError):
        user_message = f"{message}：输入数据格式错误"
    elif isinstance(e, KeyError):
        user_message = f"{message}：缺少必要的数据字段"
    elif isinstance(e, FileNotFoundError):
        user_message = f"{message}：找不到所需文件"
    else:
        user_message = f"{message}：操作失败"

    # 记录详细的技术错误信息到日志
    logger.log(
        level, f"{message}: {type(e).__name__}: {str(e)}", exc_info=True)

    # 向用户显示友好的错误消息
    print(user_message)
    return user_message


def calculate_optimal_threads():
    """
    根据 CPU 负载和内存使用情况计算最佳线程数，增加了安全边界。

    返回:
        int: 推荐的线程数量
    """
    try:
        # 获取当前系统的CPU和内存使用率
        cpu_usage = psutil.cpu_percent(interval=1)  # 增加采样时间提高准确性
        mem_usage = psutil.virtual_memory().percent
        cpu_count = os.cpu_count() or 4  # 提供默认值

        logger.info(
            f"系统状态 - CPU使用率: {cpu_usage}%, 内存使用率: {mem_usage}%, CPU核心数: {cpu_count}")

        # 根据系统负载动态调整线程数
        if cpu_usage > 80 or mem_usage > 85:
            # 系统负载高时，使用保守的线程数
            max_threads = max(1, cpu_count // 2)
        elif cpu_usage < 20 and mem_usage < 50:
            # 系统负载低时，可以使用更多线程
            max_threads = cpu_count * 3
        else:
            # 中等负载时，使用适中的线程数
            max_threads = cpu_count * 2

        # 安全边界：确保线程数在合理范围内
        max_threads = max(1, min(max_threads, cpu_count * 4, 32))  # 最大不超过32个线程

        logger.info(f"计算得出最佳线程数: {max_threads}")
        return int(max_threads)

    except Exception as e:
        logger.warning(f"计算最佳线程数失败，使用默认值: {e}")
        return 4  # 保守的默认值


def format_file_size(size_bytes):
    """
    将字节数格式化为人类可读的文件大小。

    参数:
        size_bytes (int): 文件大小（字节）

    返回:
        str: 格式化的文件大小字符串
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def get_safe_filename(filename, max_length=255):
    """
    获取安全的文件名，处理长度限制和特殊字符。

    参数:
        filename (str): 原始文件名
        max_length (int): 最大文件名长度

    返回:
        str: 安全的文件名
    """
    if not filename:
        return "unnamed_file"

    # 移除非法字符
    safe_name = remove_invalid_chars(filename)

    # 处理长度限制
    if len(safe_name) > max_length:
        # 保留文件扩展名
        name_part, ext_part = os.path.splitext(safe_name)
        available_length = max_length - len(ext_part)
        if available_length > 0:
            safe_name = name_part[:available_length] + ext_part
        else:
            safe_name = safe_name[:max_length]

    return safe_name or "unnamed_file"
