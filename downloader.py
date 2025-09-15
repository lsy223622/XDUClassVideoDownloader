#!/usr/bin/env python3
"""
下载模块
负责MP4视频文件的安全下载和智能合并处理

主要功能：
- 支持断点续传的MP4视频下载
- 智能的视频文件合并和处理
- 跨平台的下载支持和错误恢复
- 进度跟踪和用户友好的反馈
- 完整的异常处理和资源管理

安全特性：
- 文件完整性验证
- 原子性文件操作
- 临时文件自动清理
- 下载重试机制
"""

import subprocess
import re
import requests
import shutil
import tempfile
import threading
import math
import sys
import os
import csv
import time
import concurrent.futures
from pathlib import Path
from threading import Lock
from tqdm import tqdm
from utils import day_to_chinese, handle_exception, get_safe_filename, format_file_size, remove_invalid_chars, create_directory, calculate_optimal_threads, setup_logging
from config import get_auth_cookies, format_auth_cookies
from validator import is_valid_url, validate_file_integrity as verify_file_integrity
from api import FID, get_initial_data, fetch_video_links

# 配置日志（统一到模块日志 + 总日志；控制台仅 error+）
logger = setup_logging('downloader')

# 下载配置
CHUNK_SIZE = 8192  # 下载块大小
DOWNLOAD_TIMEOUT = 60  # 下载超时时间（秒）
MAX_DOWNLOAD_RETRIES = 3  # 最大下载重试次数
MIN_FILE_SIZE = 1024  # 最小有效文件大小（字节）
MAX_THREADS_PER_FILE = 32  # 每个文件的最大并发分片数
MIN_SIZE_FOR_MULTITHREAD = 10 * 1024 * 1024  # 启用多线程下载的最小文件大小（10MB）


def download_mp4(url, filename, save_dir, max_attempts=MAX_DOWNLOAD_RETRIES):
    """
    下载MP4视频文件，支持断点续传和完整性验证。

    参数:
        url (str): MP4视频文件的URL
        filename (str): 保存的文件名
        save_dir (str): 保存目录
        max_attempts (int): 最大重试次数

    返回:
        bool: 下载是否成功

    异常:
        ValueError: 当参数无效时
        OSError: 当文件操作失败时
    """
    # 参数验证
    if not url or not isinstance(url, str):
        raise ValueError("URL不能为空且必须是字符串类型")

    if not is_valid_url(url):
        logger.warning(f"URL格式可能无效: {url}")

    if not filename or not isinstance(filename, str):
        raise ValueError("文件名不能为空且必须是字符串类型")

    if not save_dir or not isinstance(save_dir, str):
        raise ValueError("保存目录不能为空且必须是字符串类型")

    # 确保文件名安全
    safe_filename = get_safe_filename(filename)
    output_path = Path(save_dir) / safe_filename

    # 检查文件是否已存在且完整
    if output_path.exists():
        if verify_file_integrity(str(output_path)):
            logger.info(f"文件已存在且完整，跳过下载: {safe_filename}")
            return True
        else:
            logger.warning(f"文件已存在但不完整，将重新下载: {safe_filename}")
            try:
                output_path.unlink()
            except OSError as e:
                logger.warning(f"删除不完整文件失败: {e}")

    # 创建保存目录
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"无法创建保存目录: {e}")

    # 获取认证头
    try:
        auth_cookies = get_auth_cookies(FID)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "video/mp4,video/*,*/*;q=0.9",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cookie": format_auth_cookies(auth_cookies),
            "Referer": "http://newes.chaoxing.com/",
            "Cache-Control": "no-cache"
        }
    except Exception as e:
        logger.error(f"获取认证信息失败: {e}")
        raise ValueError(f"无法获取认证信息: {e}")

    # 重试下载机制
    for attempt in range(max_attempts):
        temp_path = None
        try:
            logger.info(f"开始下载 ({attempt + 1}/{max_attempts}): {safe_filename}")

            # 首先发送HEAD请求获取文件信息
            try:
                logger.debug(f"HEAD {url}")
                head_response = requests.head(url, headers=headers, allow_redirects=True, timeout=DOWNLOAD_TIMEOUT)
                head_response.raise_for_status()

                total_size = int(head_response.headers.get('content-length', 0))
                content_type = head_response.headers.get('content-type', '')
                accept_ranges = head_response.headers.get('accept-ranges', '')

                # 验证内容类型
                if content_type and 'video' not in content_type and 'octet-stream' not in content_type:
                    logger.warning(f"内容类型可能不正确: {content_type}")

                logger.info(f"文件大小: {format_file_size(total_size) if total_size > 0 else '未知'}")

            except requests.RequestException as e:
                logger.warning(f"获取文件信息失败，继续下载: {e}")
                total_size = 0
                accept_ranges = ''

            # 创建临时文件
            temp_path = output_path.with_suffix('.tmp')

            # 如果服务器支持 Range 且文件较大，则使用多线程分片下载
            use_multithread = (total_size >= MIN_SIZE_FOR_MULTITHREAD and accept_ranges and 'bytes' in accept_ranges.lower())

            if use_multithread:
                # Determine number of threads
                num_threads = min(MAX_THREADS_PER_FILE, max(1, math.ceil(total_size / (MIN_SIZE_FOR_MULTITHREAD))))
                num_threads = min(num_threads, MAX_THREADS_PER_FILE)

                # split ranges
                part_size = total_size // num_threads

                # prepare part files
                part_paths = [temp_path.with_suffix(f'.part{idx}') for idx in range(num_threads)]
                downloaded_lock = threading.Lock()
                downloaded_total = {'value': 0}

                fail_parts = []  # 记录失败的分片索引

                def worker(idx, start, end, part_path):
                    headers_local = headers.copy()
                    headers_local['Range'] = f'bytes={start}-{end}'
                    attempts_local = 0
                    while attempts_local < max_attempts:
                        try:
                            logger.debug(f"GET {url} Range={start}-{end} (part {idx})")
                            with requests.get(url, headers=headers_local, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                                r.raise_for_status()
                                with open(part_path, 'wb') as pf:
                                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            pf.write(chunk)
                                            with downloaded_lock:
                                                downloaded_total['value'] += len(chunk)
                            return True
                        except Exception as e:
                            attempts_local += 1
                            logger.warning(f"分片 {idx} 下载失败，重试 {attempts_local}/{max_attempts}: {e}")
                    # 记录失败（不抛异常，避免线程级大量 traceback 噪音）
                    fail_parts.append(idx)
                    return False

                # start threads
                threads = []
                for i in range(num_threads):
                    start = i * part_size
                    end = (start + part_size - 1) if i < num_threads - 1 else (total_size - 1)
                    t = threading.Thread(target=worker, args=(i, start, end, part_paths[i]), daemon=True)
                    threads.append(t)
                    t.start()

                # show progress
                with tqdm(total=total_size, desc=safe_filename, unit='B', unit_scale=True, leave=False) as pbar:
                    prev = 0
                    while any(t.is_alive() for t in threads):
                        with downloaded_lock:
                            cur = downloaded_total['value']
                        delta = cur - prev
                        if delta > 0:
                            pbar.update(delta)
                            prev = cur
                        for t in threads:
                            t.join(timeout=0.1)
                    # final update
                    with downloaded_lock:
                        cur = downloaded_total['value']
                    if cur - prev > 0:
                        pbar.update(cur - prev)

                # ensure threads finished
                for t in threads:
                    if t.is_alive():
                        t.join()

                # 如果有失败的分片，回退到单线程下载
                if fail_parts:
                    logger.warning(f"检测到 {len(fail_parts)} 个分片下载失败，回退到单线程下载：{fail_parts}")
                    # 清理已下载分片
                    for p in part_paths:
                        if p.exists():
                            try:
                                p.unlink()
                            except Exception:
                                pass
                    # 改为普通单线程下载逻辑（与下面 else 分支基本相同）
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass

                    logger.debug(f"GET {url} (fallback single-thread after parts) ")
                    response = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
                    response.raise_for_status()
                    if total_size == 0:
                        total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    with open(temp_path, 'wb') as f:
                        if total_size > 0:
                            with tqdm(total=total_size, unit='B', unit_scale=True, desc=safe_filename, leave=False) as pbar:
                                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        pbar.update(len(chunk))
                        else:
                            with tqdm(unit='B', unit_scale=True, desc=safe_filename, leave=False) as pbar:
                                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        pbar.update(len(chunk))
                else:
                    # 合并分片到临时文件
                    with open(temp_path, 'wb') as out_f:
                        for p in part_paths:
                            if not p.exists():
                                raise Exception(f"缺失分片文件: {p}")
                            with open(p, 'rb') as pf:
                                shutil.copyfileobj(pf, out_f)

                    # 删除分片文件
                    for p in part_paths:
                        try:
                            p.unlink()
                        except Exception:
                            logger.debug(f"无法删除分片文件: {p}")

            else:
                # 单线程/断点续传逻辑（保持原本行为）
                resume_pos = 0
                if temp_path.exists():
                    resume_pos = temp_path.stat().st_size
                    if resume_pos > 0 and total_size > 0 and resume_pos < total_size:
                        logger.info(f"检测到未完成的下载，从 {format_file_size(resume_pos)} 处继续")
                        headers['Range'] = f'bytes={resume_pos}-'
                    else:
                        # 删除无效的临时文件
                        temp_path.unlink()
                        resume_pos = 0

                # 发送GET请求下载文件
                response = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
                response.raise_for_status()

                # 更新总大小（如果之前没有获取到）
                if total_size == 0:
                    total_size = int(response.headers.get('content-length', 0))

                # 下载文件
                downloaded_size = resume_pos
                with open(temp_path, 'ab' if resume_pos > 0 else 'wb') as f:
                    if total_size > 0:
                        with tqdm(
                            total=total_size,
                            initial=downloaded_size,
                            unit='B',
                            unit_scale=True,
                            desc=safe_filename,
                            leave=False
                        ) as pbar:
                            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    pbar.update(len(chunk))
                    else:
                        # 如果无法获取文件大小，显示简单进度
                        with tqdm(
                            unit='B',
                            unit_scale=True,
                            desc=safe_filename,
                            leave=False
                        ) as pbar:
                            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    pbar.update(len(chunk))

            # 验证下载的文件
            if not verify_file_integrity(str(temp_path), total_size if total_size > 0 else None):
                raise ValueError("下载的文件验证失败")

            # 原子性重命名
            shutil.move(str(temp_path), str(output_path))

            logger.info(
                f"下载完成: {safe_filename} ({format_file_size(output_path.stat().st_size)})")
            return True

        except requests.Timeout:
            error_msg = f"下载超时 ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(Exception("下载超时"), f"下载 {safe_filename} 失败")

        except requests.ConnectionError:
            error_msg = f"网络连接错误 ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(Exception("网络连接失败"), f"下载 {safe_filename} 失败")

        except requests.HTTPError as e:
            error_msg = f"HTTP错误 {e.response.status_code} ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if e.response.status_code in [404, 403, 410]:
                # 对于客户端错误，不需要重试
                handle_exception(e, f"下载 {safe_filename} 失败：资源不可用")
                break
            if attempt == max_attempts - 1:
                handle_exception(e, f"下载 {safe_filename} 失败")

        except Exception as e:
            error_msg = f"下载失败 ({attempt + 1}/{max_attempts}): {safe_filename}, 错误: {e}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(e, f"下载 {safe_filename} 最终失败")

        finally:
            # 清理临时文件（下载失败时）
            if temp_path and temp_path.exists() and not output_path.exists():
                try:
                    # 保留临时文件用于断点续传，但如果是最后一次尝试则删除
                    if attempt == max_attempts - 1:
                        temp_path.unlink()
                        logger.debug(f"已清理临时文件: {temp_path}")
                except OSError as e:
                    logger.warning(f"清理临时文件失败: {e}")

    return False


# 使用 ANSI 控制序列的覆盖打印实现（上移一行并清空），参考示例中的 "\033[F\033[K" 方法。
# 该实现以换行方式输出临时状态（与示例保持一致），随后可调用 clear_overwrite_line()
# 将上一条临时状态清除。为提高在旧版 Windows 控制台的兼容性，尝试开启 VT 模式。

_last_overwrite = False


def _enable_windows_ansi():
    """在 Windows 上尝试开启虚拟终端处理，启用 ANSI 转义序列支持。"""
    if os.name != 'nt':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        hStdOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(hStdOut, new_mode)
    except Exception:
        # 若无法开启也无需中断，ANSI 在多数现代终端可用
        pass


# 尝试启用（在模块导入时运行一次）
_enable_windows_ansi()


def overwrite_print(msg):
    """打印一行临时状态（带换行），后续可调用 clear_overwrite_line() 清除该行。"""
    global _last_overwrite
    print(str(msg))
    sys.stdout.flush()
    _last_overwrite = True


def clear_overwrite_line():
    """如果上一次输出是通过 overwrite_print 打印的，向上移动一行并清空该行。"""
    global _last_overwrite
    if _last_overwrite:
        # 上移一行并清空该行（ESC[F 上移，ESC[K 清除行）
        sys.stdout.write('\033[F\033[K')
        sys.stdout.flush()
        _last_overwrite = False


def check_ffmpeg_availability():
    """
    检查系统是否安装了FFmpeg。

    返回:
        bool: FFmpeg是否可用
    """
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=10)
        logger.debug("FFmpeg可用")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("FFmpeg不可用")
        return False


def merge_videos(files, output_file):
    """
    使用FFmpeg合并多个MP4视频文件，包含完整的错误处理和验证。

    参数:
        files (list): 要合并的视频文件路径列表
        output_file (str): 输出文件路径

    返回:
        bool: 合并是否成功

    异常:
        ValueError: 当参数无效时
        OSError: 当文件操作失败时
    """
    # 参数验证
    if not files or not isinstance(files, list):
        raise ValueError("文件列表不能为空且必须是列表类型")

    if len(files) < 2:
        logger.warning("文件数量少于2个，无需合并")
        return False

    if not output_file or not isinstance(output_file, str):
        raise ValueError("输出文件路径不能为空且必须是字符串类型")

    # 检查FFmpeg可用性
    if not check_ffmpeg_availability():
        handle_exception(
            Exception("FFmpeg不可用"),
            "无法合并视频文件：未找到FFmpeg。请安装FFmpeg以启用视频合并功能"
        )
        return False

    # 验证输入文件
    valid_files = []
    missing_files = []

    for file_path in files:
        if not isinstance(file_path, str):
            logger.warning(f"跳过无效的文件路径: {file_path}")
            continue

        path_obj = Path(file_path)
        if path_obj.exists():
            if verify_file_integrity(str(path_obj)):
                valid_files.append(str(path_obj.resolve()))
            else:
                logger.warning(f"文件验证失败，跳过: {file_path}")
        else:
            missing_files.append(file_path)

    if missing_files:
        logger.warning(f"以下文件不存在，跳过: {missing_files}")

    if len(valid_files) < 2:
        logger.warning("有效文件数量不足，无法进行合并")
        return False

    # 确保输出目录存在
    output_path = Path(output_file)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"无法创建输出目录: {e}")

    # 创建临时文件列表
    temp_list_file = None
    temp_output_file = None

    try:
        # 创建临时的文件列表文件
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            delete=False,
            dir=output_path.parent,
            prefix=f'.{output_path.name}.filelist.',
            suffix='.txt'
        ) as temp_file:
            temp_list_file = temp_file.name

            # 写入文件列表，按文件名排序确保正确的合并顺序
            valid_files.sort(key=lambda f: Path(f).name)
            for file_path in valid_files:
                # 使用绝对路径并转义，确保FFmpeg能正确处理
                escaped_path = str(Path(file_path).resolve()).replace("'", r"\'").replace("\\", "/")
                temp_file.write(f"file '{escaped_path}'\n")

        logger.info(f"准备合并 {len(valid_files)} 个文件到: {output_file}")

        # 创建临时输出文件
        temp_output_file = str(output_path.with_suffix('.tmp' + output_path.suffix))

        # 构建FFmpeg命令
        ffmpeg_cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', temp_list_file,
            '-c', 'copy',  # 直接复制，不重新编码
            '-avoid_negative_ts', 'make_zero',  # 处理时间戳问题
            '-y',  # 覆盖输出文件
            temp_output_file
        ]

        logger.debug(f"执行FFmpeg命令: {' '.join(ffmpeg_cmd)}")

        # 执行FFmpeg合并
        try:
            result = subprocess.run(
                ffmpeg_cmd,
                check=True,
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                timeout=600  # 10分钟超时
            )

            logger.debug(f"FFmpeg输出: {result.stderr}")

        except subprocess.TimeoutExpired:
            raise Exception("视频合并超时")
        except subprocess.CalledProcessError as e:
            error_output = e.stderr if e.stderr else str(e)
            raise Exception(f"FFmpeg执行失败: {error_output}")

        # 验证合并后的文件
        if not verify_file_integrity(temp_output_file):
            raise Exception("合并后的文件验证失败")

        # 原子性移动到最终位置
        shutil.move(temp_output_file, output_file)

        logger.info(f"视频合并完成: {output_file}")

        # 合并成功后删除原始文件
        for file_path in valid_files:
            try:
                Path(file_path).unlink()
                logger.debug(f"已删除原始文件: {file_path}")
            except OSError as e:
                logger.warning(f"删除原始文件失败: {file_path}, 错误: {e}")

        return True

    except Exception as e:
        error_msg = f"合并视频失败: {e}"
        logger.error(error_msg)
        handle_exception(e, f"合并 {output_file} 失败")
        return False

    finally:
        # 清理临时文件
        for temp_file in [temp_list_file, temp_output_file]:
            if temp_file and Path(temp_file).exists():
                try:
                    Path(temp_file).unlink()
                    logger.debug(f"已清理临时文件: {temp_file}")
                except OSError as e:
                    logger.warning(f"清理临时文件失败: {temp_file}, 错误: {e}")


def process_rows(rows, course_code, course_name, year, save_dir, merge=True, video_type='both'):
    """
    处理视频行数据，下载视频并可选择性地合并相邻节次的视频。
    包含完整的错误处理、进度跟踪和数据验证。

    参数:
        rows (list): 视频信息行列表，每行包含[月, 日, 星期, 节次, 周数, ppt_video_url, teacher_track_url]
        course_code (str): 课程代码
        course_name (str): 课程名称
        year (int): 年份
        save_dir (str): 保存目录
        merge (bool): 是否自动合并相邻节次的视频
        video_type (str): 视频类型('both', 'ppt', 'teacher')

    返回:
        dict: 处理结果统计信息

    异常:
        ValueError: 当参数无效时
    """
    # 参数验证
    if not rows or not isinstance(rows, list):
        raise ValueError("视频行数据不能为空且必须是列表类型")

    if not course_code or not isinstance(course_code, str):
        raise ValueError("课程代码不能为空且必须是字符串类型")

    if not course_name or not isinstance(course_name, str):
        raise ValueError("课程名称不能为空且必须是字符串类型")

    if video_type not in ['both', 'ppt', 'teacher']:
        raise ValueError("视频类型必须是 'both', 'ppt' 或 'teacher'")

    # 保持简洁：已移除自定义下载命令参数

    # 确保保存目录存在
    try:
        Path(save_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"无法创建保存目录: {e}")

    # 统计信息
    stats = {
        'total_videos': 0,
        'downloaded': 0,
        'skipped': 0,
        'failed': 0,
        'merged': 0
    }

    logger.info(f"开始处理课程视频 - {course_code} {course_name} ({year}年)")
    logger.info(f"处理模式: {video_type}, 合并: {'启用' if merge else '禁用'}")

    def get_safe_filename_components(row):
        """
        从行数据中提取并验证文件名组件。

        参数:
            row (list): 视频信息行

        返回:
            tuple: (month, date, day, jie, days, day_chinese) 或 None（如果验证失败）
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

            try:
                day_chinese = day_to_chinese(day)
            except ValueError as e:
                logger.warning(f"星期转换失败: {e}")
                return None

            return month, date, day, jie, days, day_chinese

        except Exception as e:
            logger.warning(f"解析行数据时出错: {e}")
            return None

    def check_existing_files(base_filename, track_type, save_dir):
        """
        检查是否存在相关的文件（包括合并后的文件）。

        返回:
            tuple: (single_exists, merged_exists)
        """
        single_files = [
            Path(save_dir) / f"{base_filename}-{track_type}.mp4",
            Path(save_dir) / f"{base_filename}-{track_type}.ts"  # 向后兼容
        ]

        single_exists = any(f.exists() and verify_file_integrity(
            str(f)) for f in single_files)

        # 尝试解析当前的节号（例如 base_filename 中的 "第3节"）
        current_jie = None
        try:
            m = re.search(r"第(\d+)节", base_filename)
            if m:
                current_jie = int(m.group(1))
        except Exception:
            current_jie = None

        merged_exists = False
        save_path = Path(save_dir)
        # ===== 改进的合并存在判定逻辑 =====
        # 之前的实现：如果当前节号落在任意一个 “第A-B节” 文件的范围内就认定存在（忽略了“日期/周/星期”等前缀），
        # 导致不同日期但相同节次范围的文件被误判为同一天，从而跳过下载。
        # 新策略：要求“节次片段前的完整前缀”完全一致，才会进行区间覆盖判断。

        # 解析当前 base_filename 的前缀和节次区间
        # 形如：<prefix>第7节 或 <prefix>第7-8节
        range_pattern = re.compile(r'^(?P<prefix>.+?)第(?P<start>\d+)(?:-(?P<end>\d+))?节$')
        current_match = range_pattern.match(base_filename)
        if current_match:
            prefix = current_match.group('prefix')  # 含课程/日期/周/星期等完整信息
            cur_start = int(current_match.group('start'))
            cur_end = int(current_match.group('end') or current_match.group('start'))

            # 针对同一 prefix 下的所有同类型(track_type)文件进行扫描
            # 我们只关心 prefix 相同的文件（确保同一天同课程同周次）
            candidates = []
            for ext in ('.mp4', '.ts'):
                # 按 track_type 过滤，使用 glob 扫描，再用前缀精确判断
                for f in save_path.glob(f"*{track_type}{ext}"):
                    if not f.exists():
                        continue
                    name = f.name
                    if not name.endswith(f"-{track_type}{ext}"):
                        continue
                    # 去掉结尾的 -{track_type}.ext
                    # 去掉 -pptVideo.mp4 之类的部分
                    core = name[:-(len(track_type) + len(ext) + 1)]
                    # 与 base_filename 同样结构：<prefix>第X(|-Y)节
                    m2 = range_pattern.match(core)
                    if not m2:
                        continue
                    if m2.group('prefix') != prefix:
                        # 日期/周/星期不同，忽略
                        continue
                    candidates.append((f, m2))

            for f, m2 in candidates:
                try:
                    f_start = int(m2.group('start'))
                    f_end = int(m2.group('end') or m2.group('start'))
                    # 只要当前节次区间完全被文件区间覆盖即可判定已存在
                    if f_start <= cur_start and f_end >= cur_end and verify_file_integrity(str(f)):
                        merged_exists = True
                        break
                    # 兼容用户需求：如果当前是单节 (7) 允许被 (6-7) 或 (7-8) 覆盖
                    if cur_start == cur_end and verify_file_integrity(str(f)):
                        if (f_start == cur_start - 1 and f_end == cur_end) or (f_start == cur_start and f_end == cur_end + 1):
                            merged_exists = True
                            break
                except Exception:
                    continue
        else:
            # 如果无法解析（非常规命名），退回到严格的精确文件匹配（已在 single_files 中处理）
            merged_exists = False

        return single_exists, merged_exists

    def process_single_video(video_url, track_type, row):
        """
        处理单个视频的下载和合并逻辑。

        参数:
            video_url (str): 视频下载URL
            track_type (str): 视频类型标识('pptVideo'或'teacherTrack')
            row (list): 包含视频时间信息的行数据

        返回:
            dict: 处理结果 {'downloaded': bool, 'merged': bool, 'skipped': bool, 'failed': bool}
        """
        result = {'downloaded': False, 'merged': False,
                  'skipped': False, 'failed': False}

        # 验证URL
        if not video_url or not isinstance(video_url, str):
            logger.debug(f"跳过空URL: {track_type}")
            result['skipped'] = True
            return result

        if not is_valid_url(video_url):
            logger.warning(f"URL格式可能无效: {video_url}")

        # 获取文件名组件
        components = get_safe_filename_components(row)
        if not components:
            logger.error(f"无法解析行数据，跳过视频: {track_type}")
            result['failed'] = True
            return result

        month, date, day, jie, days, day_chinese = components

        # 构建基础文件名和完整文件名
        base_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节"
        filename = f"{base_filename}-{track_type}.mp4"
        filepath = Path(save_dir) / filename

        # 检查文件是否已存在
        single_exists, merged_exists = check_existing_files(base_filename, track_type, save_dir)

        if merged_exists:
            logger.info(f"合并后的视频已存在，跳过: {filename}")
            result['skipped'] = True
            return result

        if single_exists:
            logger.info(f"文件已存在，跳过下载: {filename}")
            result['skipped'] = True
        else:
            # 下载文件
            logger.info(f"开始下载: {filename}")
            try:
                download_success = download_mp4(video_url, filename, save_dir)
                if download_success:
                    result['downloaded'] = True
                    logger.info(f"下载成功: {filename}")
                else:
                    logger.error(f"下载失败: {filename}")
                    result['failed'] = True
                    return result
            except Exception as e:
                logger.error(f"下载异常: {filename}, 错误: {e}")
                result['failed'] = True
                return result

        # 合并逻辑
        if merge and filepath.exists():
            try:
                merged_result = attempt_video_merge(
                    filepath, track_type, month, date, day_chinese, jie, days, course_code, course_name, year, save_dir
                )
                if merged_result:
                    result['merged'] = True
                    logger.info(f"视频合并成功: {filename}")
            except Exception as e:
                logger.error(f"视频合并失败: {filename}, 错误: {e}")

        return result

    def attempt_video_merge(filepath, track_type, month, date, day_chinese, jie, days, course_code, course_name, year, save_dir):
        """
        尝试将当前视频与相邻节次的视频合并。

        返回:
            bool: 是否成功合并
        """
        # 查找相邻文件
        adjacent_files = []
        save_path = Path(save_dir)

        # 检查前一节和后一节
        for adjacent_jie in [jie - 1, jie + 1]:
            if adjacent_jie < 1:
                continue

            for ext in ['.mp4', '.ts']:
                adjacent_file = save_path / \
                    f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{adjacent_jie}节-{track_type}{ext}"
                if adjacent_file.exists() and verify_file_integrity(str(adjacent_file)):
                    adjacent_files.append(str(adjacent_file))
                    break

        if not adjacent_files:
            logger.debug(f"没有找到相邻的视频文件: {filepath.name}")
            return False

        # 准备合并
        all_files = adjacent_files + [str(filepath)]
        all_files.sort(key=lambda f: int(re.search(r"第(\d+)节", f).group(1)))

        # 生成合并后的文件名
        jie_numbers = [int(re.search(r"第(\d+)节", f).group(1)) for f in all_files]
        merged_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{min(jie_numbers)}-{max(jie_numbers)}节-{track_type}.mp4"
        merged_filepath = save_path / merged_filename

        # 检查合并后的文件是否已存在
        if merged_filepath.exists() and verify_file_integrity(str(merged_filepath)):
            logger.info(f"合并后的文件已存在: {merged_filename}")
            return True

        # 执行合并
        logger.info(f"合并视频文件: {[Path(f).name for f in all_files]} -> {merged_filename}")
        return merge_videos(all_files, str(merged_filepath))

    # 处理所有视频
    total_tasks = 0
    if video_type in ['both', 'ppt']:
        total_tasks += len(rows)
    if video_type in ['both', 'teacher']:
        total_tasks += len(rows)

    stats['total_videos'] = total_tasks

    with tqdm(total=total_tasks, desc="处理视频", unit="个") as pbar:
        for i, row in enumerate(rows):
            try:
                logger.debug(f"处理第 {i+1}/{len(rows)} 行数据")

                # 处理PPT视频
                if video_type in ['both', 'ppt']:
                    result = process_single_video(row[5], 'pptVideo', row)
                    if result['downloaded']:
                        stats['downloaded'] += 1
                    if result['skipped']:
                        stats['skipped'] += 1
                    if result['failed']:
                        stats['failed'] += 1
                    if result['merged']:
                        stats['merged'] += 1
                    pbar.update(1)

                # 处理教师视频
                if video_type in ['both', 'teacher']:
                    result = process_single_video(row[6], 'teacherTrack', row)
                    if result['downloaded']:
                        stats['downloaded'] += 1
                    if result['skipped']:
                        stats['skipped'] += 1
                    if result['failed']:
                        stats['failed'] += 1
                    if result['merged']:
                        stats['merged'] += 1
                    pbar.update(1)

            except Exception as e:
                logger.error(f"处理第 {i+1} 行数据时出错: {e}")
                stats['failed'] += 1
                pbar.update(1)

    # 输出处理结果
    logger.info("视频处理完成！")
    logger.info(f"统计信息: 总计 {stats['total_videos']} 个视频")
    logger.info(f"  - 新下载: {stats['downloaded']} 个")
    logger.info(f"  - 跳过: {stats['skipped']} 个")
    logger.info(f"  - 失败: {stats['failed']} 个")
    logger.info(f"  - 合并: {stats['merged']} 个")

    if stats['failed'] > 0:
        logger.warning(f"有 {stats['failed']} 个视频处理失败，请检查网络连接或重试")

    return stats


def download_single_video(row, course_code, course_name, year, save_dir, video_type):
    """
    下载单个视频片段（半节课模式）。

    参数:
        row (list): 视频信息行
        course_code (str): 课程代码
        course_name (str): 课程名称
        year (int): 年份
        save_dir (str): 保存目录
        video_type (str): 视频类型

    返回:
        bool: 下载是否成功
    """
    try:
        month, date, day, jie, days, ppt_video, teacher_track = row
        day_chinese = day_to_chinese(day)

        success_count = 0
        total_count = 0

        # 下载PPT视频
        if video_type in ['both', 'ppt'] and ppt_video:
            total_count += 1
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo.mp4"
            filepath = Path(save_dir) / filename

            if filepath.exists():
                print(f"PPT视频已存在，跳过下载：{filename}")
                success_count += 1
            else:
                print(f"开始下载PPT视频：{filename}")
                if download_mp4(ppt_video, filename, save_dir):
                    success_count += 1
                    print(f"PPT视频下载成功：{filename}")
                else:
                    print(f"PPT视频下载失败：{filename}")

        # 下载教师视频
        if video_type in ['both', 'teacher'] and teacher_track:
            total_count += 1
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-teacherTrack.mp4"
            filepath = Path(save_dir) / filename

            if filepath.exists():
                print(f"教师视频已存在，跳过下载：{filename}")
                success_count += 1
            else:
                print(f"开始下载教师视频：{filename}")
                if download_mp4(teacher_track, filename, save_dir):
                    success_count += 1
                    print(f"教师视频下载成功：{filename}")
                else:
                    print(f"教师视频下载失败：{filename}")

        print(f"\n半节课下载完成：成功 {success_count}/{total_count} 个视频")
        return success_count == total_count

    except Exception as e:
        error_msg = handle_exception(e, "半节课下载失败")
        print(f"\n{error_msg}")
        return False


        


def download_course_videos(live_id, single=0, merge=True, video_type='both', skip_until=0):
    """
    下载指定课程的视频，这是核心的下载逻辑函数。

    参数:
        live_id: 课程直播ID
        single: 下载模式 (0=全部, 1=单节课, 2=半节课)
        merge: 是否自动合并相邻节次视频
        video_type: 视频类型 ('both', 'ppt', 'teacher')
        skip_until: 跳过指定周数之前的视频

    返回:
        bool: 处理是否成功
    """
    try:
        logger.info(f"开始下载课程 {live_id} 的视频")

        # 获取课程的初始数据
        overwrite_print(f"正在获取课程 {live_id} 的信息...")
        try:
            data = get_initial_data(live_id)
        except Exception as e:
            error_msg = handle_exception(e, "获取课程信息失败")
            # 清除上一条临时状态行再打印多行信息
            clear_overwrite_line()
            print(f"\n{error_msg}")
            print("请检查：")
            print("1. 课程ID是否正确")
            print("2. 网络连接是否正常")
            print("3. 是否已正确配置认证信息")
            return False

        # 检查是否获取到有效数据
        if not data:
            clear_overwrite_line()
            print(f"\n没有找到课程 {live_id} 的数据，请检查课程ID是否正确")
            return False

        clear_overwrite_line()
        print(f"成功获取到 {len(data)} 条课程记录")

        # 处理不同的下载模式
        if single:
            original_data = data[:]
            # 筛选出指定 liveId 的条目（谨慎处理类型差异：entry['id'] 可能为 int，而 live_id 可能为 str）
            live_id_str = str(live_id)
            data = [entry for entry in original_data if str(entry.get("id", "")) == live_id_str]

            if not data:
                logger.error(f"没有找到课程ID {live_id} 对应的课程记录")
                print(f"错误：没有找到课程ID {live_id} 对应的课程记录")
                return False

            if single == 1:
                # 单节课模式：下载同一天的所有课程（根据第一个匹配条目的日期/月进行过滤）
                start_time = data[0].get("startTime", {})
                data = [
                    entry for entry in original_data
                    if (entry.get("startTime", {}).get("date") == start_time.get("date") and
                        entry.get("startTime", {}).get("month") == start_time.get("month"))
                ]
                print(f"单节课模式：将下载 {len(data)} 个视频片段")

        # 提取课程基本信息
        first_entry = data[0]
        year = time.gmtime(first_entry["startTime"]["time"] / 1000).tm_year
        course_code = first_entry.get("courseCode", "未知课程")
        course_name = remove_invalid_chars(first_entry.get("courseName", "未知课程名"))

        save_dir = f"{year}年{course_code}{course_name}"

        clear_overwrite_line()
        print(f"年份：{year}")
        print(f"课程代码：{course_code}")
        print(f"课程名称：{course_name}")
        print(f"保存目录：{save_dir}")

        # 创建保存目录
        try:
            create_directory(save_dir)
        except OSError as e:
            error_msg = handle_exception(e, "创建保存目录失败")
            print(f"\n{error_msg}")
            return False

        # 多线程获取所有视频链接
        overwrite_print(f"正在获取视频链接...")
        rows = []
        lock = Lock()

        # 只处理已结束的课程
        valid_entries = [
            entry for entry in data
            if entry.get("endTime", {}).get("time", 0) / 1000 <= time.time()
        ]

        if not valid_entries:
            print("没有找到已结束的课程，无法下载")
            return False

        clear_overwrite_line()
        print(f"找到 {len(valid_entries)} 个可下载的课程片段")

        with tqdm(total=len(valid_entries), desc="获取视频链接") as desc:
            # 计算最佳线程数
            max_threads = calculate_optimal_threads()
            logger.info(f"使用 {max_threads} 个线程获取视频链接")

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                # 提交所有任务
                futures = [
                    executor.submit(fetch_video_links, entry, lock, desc)
                    for entry in valid_entries
                ]

                # 收集所有线程的结果
                for future in concurrent.futures.as_completed(futures):
                    try:
                        row = future.result()
                        if row:
                            rows.append(row)
                    except Exception as e:
                        logger.error(f"获取视频链接时出错: {e}")

        if not rows:
            print("没有成功获取到任何视频链接")
            return False

        # 按时间排序：月、日、星期、节次、周数
        rows.sort(key=lambda x: (x[0], x[1], x[2], int(x[3]), x[4]))

        # 根据skip_until参数过滤掉指定周数之前的视频
        if skip_until > 0:
            original_count = len(rows)
            rows = [row for row in rows if int(row[4]) > skip_until]
            filtered_count = original_count - len(rows)
            if filtered_count > 0:
                print(f"根据设置跳过了前 {skip_until} 周的 {filtered_count} 个视频")

        # 保存视频信息到CSV文件（保存到 logs/ 目录以便集中管理日志/元数据）
        try:
            logs_dir = Path('logs')
            logs_dir.mkdir(parents=True, exist_ok=True)
            csv_filename = logs_dir / f"{save_dir}.csv"
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['month', 'date', 'day', 'jie', 'days', 'pptVideo', 'teacherTrack'])
                writer.writerows(rows)
            print(f"视频信息已保存到：{csv_filename}")
            logger.info(f"视频信息CSV已保存: {csv_filename}")
        except Exception as e:
            logger.warning(f"保存CSV文件失败: {e}")

        # 根据下载模式执行不同的下载逻辑
        if single == 1:
            # 单节课模式：最多下载2个条目（上下半节课）
            download_rows = rows[:2]
            print(f"\n单节课模式：准备下载 {len(download_rows)} 个视频片段")
        elif single == 2:
            # 半节课模式：只下载第一个条目
            download_rows = rows[:1]
            print(f"\n半节课模式：准备下载 1 个视频片段")
        else:
            # 全部下载模式
            download_rows = rows
            print(f"\n全部下载模式：准备下载 {len(download_rows)} 个视频片段")

        if single == 2:
            # 半节课模式的特殊处理
            return download_single_video(download_rows[0], course_code, course_name, year, save_dir, video_type)
        else:
            # 批量下载处理
            try:
                stats = process_rows(download_rows, course_code, course_name, year, save_dir, merge, video_type)

                print(f"\n下载任务完成！")
                print(f"总计 {stats['total_videos']} 个 | 下载 {stats['downloaded']} 个 | 跳过 {stats['skipped']} 个 | 失败 {stats['failed']} 个 | 合并 {stats['merged']} 个")

                if stats['failed'] > 0:
                    print(f"\n注意：有 {stats['failed']} 个视频下载失败")
                    print("可能的原因：网络连接问题、服务器限制或认证过期")
                    return False

                return True

            except Exception as e:
                error_msg = handle_exception(e, "批量下载处理失败")
                print(f"\n{error_msg}")
                return False

    except Exception as e:
        error_msg = handle_exception(e, f"下载课程 {live_id} 失败")
        logger.error(error_msg)
        print(f"\n{error_msg}")
        return False


def process_all_courses(config, video_type='both'):
    """
    处理配置文件中的所有课程。

    参数:
        config: 配置对象
        video_type: 视频类型

    返回:
        bool: 是否成功处理
    """
    success_count = 0
    total_count = 0

    for section_name in config.sections():
        section = config[section_name]
        if section.get('download', 'yes').lower() != 'yes':
            continue

        live_id = section.get('live_id')
        course_code = section.get('course_code', 'Unknown')
        course_name = section.get('course_name', 'Unknown')

        total_count += 1

        if not live_id:
            logger.warning(f"课程 {course_code} {course_name} 缺少 live_id")
            continue

        overwrite_print(f"\n正在处理课程: {course_code} {course_name}")

        try:
            # 下载课程视频 - 使用提取的核心下载函数
            clear_overwrite_line()
            success = download_course_videos(live_id, single=0, merge=True, video_type=video_type)
            if success:
                success_count += 1
            else:
                clear_overwrite_line()
                print(f"\n课程 {course_code} {course_name} 下载失败")

        except Exception as e:
            clear_overwrite_line()
            error_msg = handle_exception(e, f"处理课程失败 ({course_code} {course_name})")
            logger.error(error_msg)
            print(f"\n课程 {course_code} {course_name} 处理时发生错误: {error_msg}")

        # 添加分隔符（先清除临时行）
        clear_overwrite_line()
        print(f"\n" + "-" * 12)

    print(f"\n批量下载完成: 成功 {success_count}/{total_count} 门课程")
    return success_count > 0
