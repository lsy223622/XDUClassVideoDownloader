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

import logging
import math
import os
import stat
import sys
from pathlib import Path
from typing import Callable, Optional, Set, Union

import psutil

# ========== 统一日志系统 ==========
# 控制是否将 DEBUG 级别输出到单独文件（默认关闭），通过主程序/自动化脚本的命令行参数 --debug 启用。
DEBUG_LOG_TO_FILE = False

_GLOBAL_LOGGING_INITIALIZED = False


class NoExceptionInfoFilter(logging.Filter):
    """
    自定义日志过滤器，用于阻止异常 traceback 信息输出到控制台。

    此过滤器会移除日志记录中的 exc_info、exc_text 和 stack_info，
    使控制台只显示简洁的错误消息，而文件日志仍保留完整的调试信息。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录，移除异常信息。"""
        # 移除异常 traceback 信息
        record.exc_info = None
        record.exc_text = None
        # Python 3.8+ 也需要清理 stack_info
        if hasattr(record, "stack_info"):
            record.stack_info = None
        return True


def _ensure_global_handlers(
    console_level: int = logging.ERROR, info_file: Optional[Path] = None, debug_file: Optional[Path] = None
) -> None:
    """初始化全局/root 日志处理器：
    - 控制台：error 及以上
    - 总日志：info 及以上
    - 可选 debug 日志：debug 及以上
    该函数只在首次调用时生效，防止重复添加处理器。
    """
    global _GLOBAL_LOGGING_INITIALIZED
    if _GLOBAL_LOGGING_INITIALIZED:
        return

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("xdu")
    root_logger.setLevel(logging.DEBUG)  # 捕获所有级别，具体输出看 handler 设置

    # 控制台 handler（仅 error+）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.set_name("xdu_console")
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    # 添加过滤器，防止 traceback 输出到控制台
    console_handler.addFilter(NoExceptionInfoFilter())
    root_logger.addHandler(console_handler)

    # 总日志（info+）
    info_path = info_file or (log_dir / "all.log")
    file_handler = logging.FileHandler(info_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.set_name("all_file")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(file_handler)

    # 可选 debug 文件（debug+）
    if DEBUG_LOG_TO_FILE:
        debug_path = debug_file or (log_dir / "debug.log")
        dbg_handler = logging.FileHandler(debug_path, encoding="utf-8")
        dbg_handler.setLevel(logging.DEBUG)
        dbg_handler.set_name("debug_file")
        dbg_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(dbg_handler)

    _GLOBAL_LOGGING_INITIALIZED = True


def enable_debug_file_logging(path: Optional[str] = None) -> None:
    """启用调试日志文件输出。通常由命令行参数 --debug 触发。
    若已开启则忽略；可指定自定义路径。
    """
    global DEBUG_LOG_TO_FILE
    if DEBUG_LOG_TO_FILE:
        return
    DEBUG_LOG_TO_FILE = True
    # 重新挂载 debug handler（若 root 已初始化）
    if _GLOBAL_LOGGING_INITIALIZED:
        root = logging.getLogger("xdu")
        # 若已存在则不重复添加
        if not any(getattr(h, "name", "") == "debug_file" for h in root.handlers):
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            debug_path = Path(path) if path else (log_dir / "debug.log")
            dbg_handler = logging.FileHandler(debug_path, encoding="utf-8")
            dbg_handler.setLevel(logging.DEBUG)
            dbg_handler.set_name("debug_file")
            dbg_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            root.addHandler(dbg_handler)


def setup_logging(name: str = "app", level: int = logging.INFO, console_level: int = logging.ERROR) -> logging.Logger:
    """
    设置并返回模块日志记录器：
    - 仅首次调用时配置全局/root 处理器（控制台、总日志、可选 debug 文件）
    - 为当前模块添加一个独立文件（info+）：logs/{name}.log

    参数:
        name (str): 模块名（会映射到 logger 名字 "xdu.{name}"）
        level: 模块文件日志级别（默认 INFO）
        console_level: 控制台日志级别（仅首次全局初始化时生效，默认 ERROR）

    返回:
        logging.Logger: 配置好的模块日志记录器
    """
    _ensure_global_handlers(console_level=console_level)

    logger_name = f"xdu.{name}" if not str(name).startswith("xdu.") else str(name)
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)  # 模块 logger 接收所有级别，输出交由 handler 控制

    # 避免重复添加模块文件 handler（按自定义 name 区分）
    handler_marker = f"xdu_module_file::{logger_name}"
    if not any(getattr(h, "name", "") == handler_marker for h in logger.handlers):
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        module_file = log_dir / f"{name}.log"
        fh = logging.FileHandler(module_file, encoding="utf-8")
        fh.setLevel(level)
        fh.set_name(handler_marker)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(fh)

    # 让模块日志向上冒泡到 root（写入总日志/控制台/调试文件）
    logger.propagate = True
    return logger


# 初始化本模块日志器
logger = setup_logging("utils")


def remove_invalid_chars(course_name: str) -> str:
    """
    移除文件名中的非法字符，确保可以在文件系统中创建文件。

    使用更安全和全面的字符过滤方法，同时保持文件名的可读性。

    参数:
        course_name (str): 原始课程名称

    返回:
        str: 移除非法字符后的课程名称。

    异常:
        ValueError: 当输入为空或处理后名称为空时
    """
    if not course_name or not isinstance(course_name, str):
        raise ValueError("课程名称不能为空且必须是字符串类型")

    # 定义 Windows/Linux 文件系统中不允许的字符
    # 包括控制字符和保留字符
    invalid_chars = ["\\", "/", ":", "*", "?", '"', "<", ">", "|", "\0"]

    # 移除控制字符 (ASCII 0-31)
    cleaned_name = "".join(char for char in course_name if ord(char) >= 32)

    # 替换非法字符为下划线，保持可读性
    for char in invalid_chars:
        cleaned_name = cleaned_name.replace(char, "_")

    # 移除首尾空白字符和点号（Windows不允许）
    cleaned_name = cleaned_name.strip(" .")

    # 检查 Windows 保留文件名
    reserved_names = (
        ["CON", "PRN", "AUX", "NUL"] + [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)]
    )

    if cleaned_name.upper() in reserved_names:
        cleaned_name = f"_{cleaned_name}"

    # 限制文件名长度，避免路径过长问题
    if len(cleaned_name) > 100:
        cleaned_name = cleaned_name[:100].rstrip()

    if not cleaned_name:
        raise ValueError("处理后的课程名称为空，请检查原始名称")

    return cleaned_name


def day_to_chinese(day: Union[int, str]) -> str:
    """
    将星期数字转换为中文表示。

    参数:
        day (Union[int, str]): 星期数字（0-6，0 代表星期日，或 1-7，1 代表星期一）。

    返回:
        str: 对应的中文星期表示。

    异常:
        ValueError: 当输入不是有效的星期数字时。
    """
    if not isinstance(day, int):
        try:
            day = int(day)
        except (TypeError, ValueError):
            raise ValueError(f"星期数字必须是整数，收到：{type(day).__name__}")

    # 星期数字到中文的映射字典 - 支持两种格式
    if day == 0:
        return "日"  # 0 代表星期日
    elif 1 <= day <= 7:
        days = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}
        return days[day]
    else:
        raise ValueError(f"星期数字必须在 0-7 范围内，收到：{day}")


def user_input_with_check(
    prompt: str,
    validator: Union[Callable[[str], bool], str],
    max_attempts: int = 3,
    error_message: str = "输入格式错误，请重新输入",
    allow_empty: bool = False,
) -> str:
    """
    带验证功能的用户输入函数，提供更好的用户体验和安全性。

    参数:
        prompt (str): 提示信息。
        validator (Union[Callable[[str], bool], str]): 验证函数或正则表达式。
        max_attempts (int): 最大尝试次数。
        error_message (str): 验证失败时的错误消息。
        allow_empty (bool): 是否允许空输入。

    返回:
    str: 验证通过的用户输入。

    异常:
        ValueError: 超过最大尝试次数时
    """
    from validator import validate_input

    attempts = 0
    while attempts < max_attempts:
        try:
            user_input = input(prompt).strip()

            # 如果允许空输入且用户直接回车，则返回空字符串
            if allow_empty and user_input == "":
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


def create_directory(directory: str) -> None:
    """
    安全地创建目录，包含权限设置和原子性保证。

    参数:
        directory (str): 要创建的目录路径。

    异常:
        OSError: 创建目录失败时。
        ValueError: 路径参数无效时。
    """
    if not directory or not isinstance(directory, str):
        raise ValueError("目录路径不能为空且必须是字符串类型")

    try:
        # 使用 Path 对象处理路径，更安全
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)

        # 设置适当的权限 (仅在Unix系统上有效)
        if os.name == "posix":
            try:
                os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
            except OSError:
                logger.warning(f"无法设置目录权限: {directory}")

        logger.info(f"目录创建成功: {directory}")

    except OSError as e:
        logger.error(f"创建目录失败: {directory}, 错误: {e}")
        raise OSError(f"无法创建目录 {directory}: {e}")


def handle_exception(e: Exception, message: str, level: int = logging.ERROR) -> str:
    """
    统一的异常处理函数，提供更安全的错误信息记录。

    参数:
        e (Exception): 异常对象
        message (str): 自定义错误消息
        level: 日志级别

    返回:
        str: 用户友好的错误消息
    """
    import requests

    # 生成用户友好的错误消息
    if isinstance(e, requests.Timeout):
        user_message = f"{message}：连接超时，请检查网络连接或稍后重试"
    elif isinstance(e, requests.ConnectionError):
        user_message = f"{message}：无法连接到服务器，请检查网络连接"
    elif isinstance(e, requests.HTTPError):
        status_code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
        if status_code == 404:
            user_message = f"{message}：资源不存在"
        elif status_code == 403:
            user_message = f"{message}：访问被拒绝，可能需要重新登录"
        elif status_code == 500:
            user_message = f"{message}：服务器内部错误"
        else:
            user_message = f"{message}：HTTP 错误 {status_code}"
    elif isinstance(e, (ConnectionError, OSError)):
        user_message = f"{message}：网络连接或文件操作失败"
    elif isinstance(e, ValueError):
        # 检查是否是特定的业务逻辑错误
        error_str = str(e)
        if "空响应" in error_str or "空" in error_str:
            user_message = f"{message}：服务器未返回有效数据，该课程可能不可用"
        else:
            user_message = f"{message}：数据格式错误"
    elif isinstance(e, KeyError):
        user_message = f"{message}：响应数据不完整"
    elif isinstance(e, FileNotFoundError):
        user_message = f"{message}：找不到所需文件"
    else:
        # 对于其他异常，提取简短的错误描述
        error_str = str(e)
        if error_str and len(error_str) < 100:
            user_message = f"{message}：{error_str}"
        else:
            user_message = f"{message}：操作失败"

    # 记录详细的技术错误信息到日志文件（带完整 traceback）
    logger.log(level, f"{message}: {type(e).__name__}: {str(e)}", exc_info=True)

    # 只在ERROR级别及以上才打印到控制台，WARNING级别只记录日志
    # 这样可以避免在下载过程中打断进度条显示
    if level >= logging.ERROR:
        print(user_message)
    return user_message


def calculate_optimal_threads() -> int:
    """
    根据 CPU 负载和内存使用情况计算最佳线程数，增加了安全边界。

    返回:
        int: 推荐的线程数量。
    """
    try:
        # 获取当前系统的CPU和内存使用率
        cpu_usage = psutil.cpu_percent(interval=1)  # 增加采样时间提高准确性
        mem_usage = psutil.virtual_memory().percent
        cpu_count = os.cpu_count() or 4  # 提供默认值

        logger.info(f"系统状态 - CPU使用率: {cpu_usage}%, 内存使用率: {mem_usage}%, CPU核心数: {cpu_count}")

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


def format_file_size(size_bytes: int) -> str:
    """
    将字节数格式化为人类可读的文件大小。

    参数:
        size_bytes (int): 文件大小（字节）

    返回:
        str: 格式化的文件大小字符串。
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def get_safe_filename(filename: str, max_length: int = 255) -> str:
    """
    获取安全的文件名，处理长度限制和特殊字符。

    参数:
        filename (str): 原始文件名。
        max_length (int): 最大文件名长度。

    返回:
        str: 安全的文件名。
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


def parse_week_ranges(week_str: str) -> Set[int]:
    """
    解析周数范围字符串，支持单个数字、范围和组合。

    格式支持：
    - 单个周数：'5' -> {5}
    - 范围：'1-5' -> {1, 2, 3, 4, 5}
    - 逗号分隔：'1,3,5' -> {1, 3, 5}
    - 组合：'1-3,7,9-11' -> {1, 2, 3, 7, 9, 10, 11}

    参数:
        week_str (str): 周数范围字符串

    返回:
        Set[int]: 包含所有要跳过的周数的集合

    异常:
        ValueError: 当格式无效时
    """
    if not week_str or not week_str.strip():
        return set()

    weeks = set()
    parts = week_str.strip().split(',')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 检查是否是范围（如 "1-5"）
        if '-' in part:
            range_parts = part.split('-')
            if len(range_parts) != 2:
                raise ValueError(f"无效的范围格式: {part}")
            try:
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
                if start <= 0 or end <= 0:
                    raise ValueError(f"周数必须是正整数: {part}")
                if start > end:
                    raise ValueError(f"范围起始值不能大于结束值: {part}")
                weeks.update(range(start, end + 1))
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(f"无效的数字: {part}")
                raise
        else:
            # 单个数字
            try:
                week = int(part)
                if week <= 0:
                    raise ValueError(f"周数必须是正整数: {part}")
                weeks.add(week)
            except ValueError:
                raise ValueError(f"无效的周数: {part}")

    return weeks
