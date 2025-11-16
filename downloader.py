#!/usr/bin/env python3
"""
下载模块
负责 MP4 视频文件的安全下载和智能合并处理

主要功能：
- 支持断点续传的 MP4 视频下载
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

import concurrent.futures
import configparser
import csv
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence, Union

import requests
from tqdm import tqdm

from api import FID, REQUEST_TIMEOUT, fetch_video_links, get_initial_data
from config import format_auth_cookies, get_auth_cookies
from utils import (
    calculate_optimal_threads,
    create_directory,
    day_to_chinese,
    format_file_size,
    get_safe_filename,
    handle_exception,
    remove_invalid_chars,
    setup_logging,
)
from validator import is_valid_url
from validator import validate_file_integrity as verify_file_integrity

# 配置日志（统一到模块日志 + 总日志；控制台仅 error+）
logger = setup_logging("downloader")

# 下载配置
CHUNK_SIZE = 8192  # 下载块大小
DOWNLOAD_TIMEOUT = 60  # 下载超时时间（秒）
MAX_DOWNLOAD_RETRIES = 3  # 最大下载重试次数
MIN_FILE_SIZE = 1024  # 最小有效文件大小（字节）
MAX_THREADS_PER_FILE = 32  # 每个文件的最大并发分片数
MIN_SIZE_FOR_MULTITHREAD = 10 * 1024 * 1024  # 启用多线程下载的最小文件大小（10MB）


def get_ffmpeg_path() -> str:
    """
    获取 FFmpeg 可执行路径，优先顺序：
    1) 环境变量指定：FFMPEG_BINARY / FFMPEG_PATH（可为绝对路径或命令名）
    2) 程序目录：
       - Windows: ffmpeg_min.exe / ffmpeg.exe
       - POSIX:   ffmpeg_min / ffmpeg（无扩展名）
    3) PATH 中的 ffmpeg（通过 shutil.which 查找）
    """

    def _ensure_posix_executable(p: Path):
        if os.name != "nt":
            try:
                mode = p.stat().st_mode
                if not (mode & stat.S_IXUSR):
                    os.chmod(p, mode | stat.S_IXUSR)
            except Exception:
                pass

    # 1) env override
    for env_key in ("FFMPEG_BINARY", "FFMPEG_PATH"):
        val = os.environ.get(env_key)
        if not val:
            continue
        try:
            p = Path(val)
            if p.exists():
                _ensure_posix_executable(p)
                return str(p)
        except Exception:
            pass
        # allow command names in PATH
        found = shutil.which(val)
        if found:
            return found

    # 2) local bundled names
    try:
        meipass = getattr(sys, "_MEIPASS", None)
    except Exception:
        meipass = None

    if meipass:
        base = Path(meipass)
    else:
        try:
            base = (
                Path(sys.executable).resolve().parent
                if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parent
            )
        except Exception:
            base = Path.cwd()
    if os.name == "nt":
        names = ("ffmpeg_min.exe", "ffmpeg.exe")
    else:
        names = ("ffmpeg_min", "ffmpeg")
    for name in names:
        p = base / name
        try:
            if p.exists():
                _ensure_posix_executable(p)
                return str(p)
        except Exception:
            pass

    # 3) PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # fallback: let subprocess resolve
    return "ffmpeg"


def download_mp4(
    url: str,
    filename: str,
    save_dir: str,
    max_attempts: int = MAX_DOWNLOAD_RETRIES,
) -> bool:
    """
    下载 MP4 视频文件，支持断点续传和完整性验证。

    参数:
        url (str): MP4 视频文件的 URL
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
        raise ValueError("URL 不能为空且必须是字符串类型")

    if not is_valid_url(url):
        logger.warning(f"URL 格式可能无效: {url}")

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
            "Cache-Control": "no-cache",
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
            total_size = 0
            accept_ranges = ""
            try:
                logger.debug(f"HEAD {url}")
                with closing(
                    requests.head(url, headers=headers, allow_redirects=True, timeout=DOWNLOAD_TIMEOUT)
                ) as head_response:
                    head_response.raise_for_status()
                    total_size = int(head_response.headers.get("content-length", 0) or 0)
                    content_type = head_response.headers.get("content-type", "")
                    accept_ranges = head_response.headers.get("accept-ranges", "")

                    # 验证内容类型
                    if content_type and "video" not in content_type and "octet-stream" not in content_type:
                        logger.warning(f"内容类型可能不正确: {content_type}")
                    logger.info(f"文件大小: {format_file_size(total_size) if total_size > 0 else '未知'}")
            except requests.RequestException as e:
                logger.warning(f"获取文件信息失败，继续下载: {e}")
                total_size = 0
                accept_ranges = ""

            # 创建临时文件
            temp_path = output_path.with_suffix(".tmp")

            # 如果服务器支持 Range 且文件较大，则使用多线程分片下载
            use_multithread = (
                total_size >= MIN_SIZE_FOR_MULTITHREAD and accept_ranges and "bytes" in accept_ranges.lower()
            )

            if use_multithread:
                num_threads = min(MAX_THREADS_PER_FILE, max(1, math.ceil(total_size / MIN_SIZE_FOR_MULTITHREAD)))
                num_threads = min(num_threads, MAX_THREADS_PER_FILE)
                part_size = total_size // num_threads
                part_paths = [temp_path.with_suffix(f".part{idx}") for idx in range(num_threads)]
                downloaded_lock = threading.Lock()
                downloaded_total = {"value": 0}
                fail_parts = []

                def worker(idx, start, end, part_path):
                    headers_local = headers.copy()
                    headers_local["Range"] = f"bytes={start}-{end}"
                    attempts_local = 0
                    while attempts_local < max_attempts:
                        try:
                            logger.debug(f"GET {url} Range={start}-{end} (part {idx})")
                            with requests.get(url, headers=headers_local, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                                r.raise_for_status()
                                with open(part_path, "wb") as pf:
                                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            pf.write(chunk)
                                            with downloaded_lock:
                                                downloaded_total["value"] += len(chunk)
                            return True
                        except Exception as e:
                            attempts_local += 1
                            logger.warning(f"分片 {idx} 下载失败，重试 {attempts_local}/{max_attempts}: {e}")
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
                with tqdm(total=total_size, desc=safe_filename, unit="B", unit_scale=True, leave=False) as pbar:
                    prev = 0
                    while any(t.is_alive() for t in threads):
                        with downloaded_lock:
                            cur = downloaded_total["value"]
                        delta = cur - prev
                        if delta > 0:
                            pbar.update(delta)
                            prev = cur
                        for t in threads:
                            t.join(timeout=0.1)
                    # final update
                    with downloaded_lock:
                        cur = downloaded_total["value"]
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
                    with closing(requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)) as response:
                        response.raise_for_status()
                        if total_size == 0:
                            total_size = int(response.headers.get("content-length", 0) or 0)
                        downloaded_size = 0
                        with open(temp_path, "wb") as f:
                            if total_size > 0:
                                with tqdm(
                                    total=total_size, unit="B", unit_scale=True, desc=safe_filename, leave=False
                                ) as pbar:
                                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            f.write(chunk)
                                            downloaded_size += len(chunk)
                                            pbar.update(len(chunk))
                            else:
                                with tqdm(unit="B", unit_scale=True, desc=safe_filename, leave=False) as pbar:
                                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            f.write(chunk)
                                            downloaded_size += len(chunk)
                                            pbar.update(len(chunk))
                else:
                    # 合并分片到临时文件
                    with open(temp_path, "wb") as out_f:
                        for p in part_paths:
                            if not p.exists():
                                raise Exception(f"缺失分片文件: {p}")
                            with open(p, "rb") as pf:
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
                added_range = False
                if temp_path.exists():
                    resume_pos = temp_path.stat().st_size
                    if resume_pos > 0 and total_size > 0 and resume_pos < total_size:
                        logger.info(f"检测到未完成的下载，从 {format_file_size(resume_pos)} 处继续")
                        headers["Range"] = f"bytes={resume_pos}-"
                        added_range = True
                    else:
                        # 删除无效的临时文件
                        temp_path.unlink()
                        resume_pos = 0

                # 发送 GET 请求下载文件
                try:
                    with closing(requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)) as response:
                        response.raise_for_status()
                        # 更新总大小（如果之前没有获取到）
                        if total_size == 0:
                            total_size = int(response.headers.get("content-length", 0) or 0)
                        # 下载文件
                        downloaded_size = resume_pos
                        with open(temp_path, "ab" if resume_pos > 0 else "wb") as f:
                            if total_size > 0:
                                with tqdm(
                                    total=total_size,
                                    initial=downloaded_size,
                                    unit="B",
                                    unit_scale=True,
                                    desc=safe_filename,
                                    leave=False,
                                ) as pbar:
                                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            f.write(chunk)
                                            downloaded_size += len(chunk)
                                            pbar.update(len(chunk))
                            else:
                                # 如果无法获取文件大小，显示简单进度
                                with tqdm(unit="B", unit_scale=True, desc=safe_filename, leave=False) as pbar:
                                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            f.write(chunk)
                                            downloaded_size += len(chunk)
                                            pbar.update(len(chunk))
                finally:
                    if added_range:
                        headers.pop("Range", None)

            # 验证下载的文件
            if not verify_file_integrity(str(temp_path), total_size if total_size > 0 else None):
                raise ValueError("下载的文件验证失败")

            # 原子性重命名
            shutil.move(str(temp_path), str(output_path))
            logger.info(f"下载完成: {safe_filename} ({format_file_size(output_path.stat().st_size)})")
            return True

        except requests.Timeout:
            error_msg = f"下载超时 ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(Exception("下载超时"), f"下载 {safe_filename} 失败", level=logging.WARNING)

        except requests.ConnectionError:
            error_msg = f"网络连接错误 ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(Exception("网络连接失败"), f"下载 {safe_filename} 失败", level=logging.WARNING)

        except requests.HTTPError as e:
            error_msg = f"HTTP错误 {e.response.status_code} ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if e.response.status_code in [404, 403, 410]:
                # 对于客户端错误，不需要重试
                handle_exception(e, f"下载 {safe_filename} 失败：资源不可用", level=logging.WARNING)
                break
            if attempt == max_attempts - 1:
                handle_exception(e, f"下载 {safe_filename} 失败", level=logging.WARNING)

        except Exception as e:
            error_msg = f"下载失败 ({attempt + 1}/{max_attempts}): {safe_filename}, 错误: {e}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(e, f"下载 {safe_filename} 最终失败", level=logging.WARNING)

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


def _enable_windows_ansi() -> None:
    """在 Windows 上尝试开启虚拟终端处理，启用 ANSI 转义序列支持。"""
    if os.name != "nt":
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


def overwrite_print(msg: str) -> None:
    """打印一行临时状态（带换行），后续可调用 clear_overwrite_line() 清除该行。"""
    global _last_overwrite
    print(str(msg))
    sys.stdout.flush()
    _last_overwrite = True


def clear_overwrite_line() -> None:
    """如果上一次输出是通过 overwrite_print 打印的，向上移动一行并清空该行。"""
    global _last_overwrite
    if _last_overwrite:
        # 上移一行并清空该行（ESC[F 上移，ESC[K 清除行）
        sys.stdout.write("\033[F\033[K")
        sys.stdout.flush()
        _last_overwrite = False


def check_ffmpeg_availability() -> bool:
    """
    检查系统是否安装了FFmpeg。

    返回:
        bool: FFmpeg是否可用
    """
    try:
        ffmpeg_bin = get_ffmpeg_path()
        result = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, check=True, timeout=10)
        logger.debug(f"FFmpeg可用: {ffmpeg_bin}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("FFmpeg不可用")
        return False


def merge_videos(files: Sequence[str], output_file: str) -> bool:
    """
    使用 FFmpeg 合并多个 MP4 视频文件，包含完整的错误处理和验证。

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
        logger.warning("文件数量少于 2 个，无需合并")
        return False

    if not output_file or not isinstance(output_file, str):
        raise ValueError("输出文件路径不能为空且必须是字符串类型")

    # 检查 FFmpeg 可用性
    if not check_ffmpeg_availability():
        handle_exception(Exception("FFmpeg 不可用"), "无法合并视频文件：未找到 FFmpeg。请安装 FFmpeg 以启用视频合并功能")
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
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=output_path.parent,
            prefix=f".{output_path.name}.filelist.",
            suffix=".txt",
        ) as temp_file:
            temp_list_file = temp_file.name

            # 写入文件列表，按节次数字排序确保正确的合并顺序
            def extract_jie_number(filepath):
                """从文件路径中提取节次数字用于排序"""
                filename = Path(filepath).name
                match = re.search(r'第(\d+)(?:-\d+)?节', filename)
                return int(match.group(1)) if match else 0
            valid_files.sort(key=extract_jie_number)
            for file_path in valid_files:
                # 使用绝对路径并转义，确保 FFmpeg 能正确处理
                escaped_path = str(Path(file_path).resolve()).replace("'", r"\'").replace("\\", "/")
                temp_file.write(f"file '{escaped_path}'\n")

        logger.info(f"准备合并 {len(valid_files)} 个文件到: {output_file}")

        # 创建临时输出文件
        temp_output_file = str(output_path.with_suffix(".tmp" + output_path.suffix))

        # 构建 FFmpeg 命令
        # 针对视频片段合并优化：保持音画同步同时容错损坏包
        ffmpeg_cmd = [
            get_ffmpeg_path(),
            "-fflags",
            "+genpts+discardcorrupt",  # 生成 PTS 时间戳，丢弃损坏的包（保留 DTS 维持音画同步）
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            temp_list_file,
            "-c",
            "copy",  # 直接复制，不重新编码
            "-avoid_negative_ts",
            "make_zero",  # 处理负时间戳，保持音画同步
            "-max_muxing_queue_size",
            "1024",  # 适度增加混流队列（默认 128，太大会增加延迟）
            "-map",
            "0:v:0",  # 只映射第一个视频流
            "-map",
            "0:a:0?",  # 只映射第一个音频流（如果存在）
            "-y",  # 覆盖输出文件
            temp_output_file,
        ]

        logger.debug(f"执行 FFmpeg 命令: {' '.join(ffmpeg_cmd)}")

        # 执行 FFmpeg 合并
        try:
            result = subprocess.run(
                ffmpeg_cmd,
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,  # 10 分钟超时
            )

            logger.debug(f"FFmpeg 输出: {result.stderr}")

        except subprocess.TimeoutExpired:
            raise Exception("视频合并超时")
        except subprocess.CalledProcessError as e:
            error_output = e.stderr if e.stderr else str(e)
            raise Exception(f"FFmpeg 执行失败: {error_output}")

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


def process_rows(
    rows: List[List[Any]],
    course_code: str,
    course_name: str,
    year: int,
    save_dir: str,
    merge: bool = True,
    video_type: str = "both",
    api_version: str = "new",
) -> Dict[str, int]:
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
        api_version (str): API 版本，"new"表示新版（mp4），"legacy"表示旧版（m3u8）

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

    if video_type not in ["both", "ppt", "teacher"]:
        raise ValueError("视频类型必须是 'both', 'ppt' 或 'teacher'")

    # 保持简洁：已移除自定义下载命令参数

    # 确保保存目录存在
    try:
        Path(save_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"无法创建保存目录: {e}")

    # 统计信息
    stats = {"total_videos": 0, "downloaded": 0, "skipped": 0, "failed": 0, "merged": 0}

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
            Path(save_dir) / f"{base_filename}-{track_type}.ts",  # 向后兼容
        ]

        single_exists = any(f.exists() and verify_file_integrity(str(f)) for f in single_files)

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
        range_pattern = re.compile(r"^(?P<prefix>.+?)第(?P<start>\d+)(?:-(?P<end>\d+))?节$")
        current_match = range_pattern.match(base_filename)
        if current_match:
            prefix = current_match.group("prefix")  # 含课程/日期/周/星期等完整信息
            cur_start = int(current_match.group("start"))
            cur_end = int(current_match.group("end") or current_match.group("start"))

            # 针对同一 prefix 下的所有同类型(track_type)文件进行扫描
            # 我们只关心 prefix 相同的文件（确保同一天同课程同周次）
            candidates = []
            for ext in (".mp4", ".ts"):
                # 按 track_type 过滤，使用 glob 扫描，再用前缀精确判断
                for f in save_path.glob(f"*{track_type}{ext}"):
                    if not f.exists():
                        continue
                    name = f.name
                    if not name.endswith(f"-{track_type}{ext}"):
                        continue
                    # 去掉结尾的 -{track_type}.ext
                    # 去掉 -pptVideo.mp4 之类的部分
                    core = name[: -(len(track_type) + len(ext) + 1)]
                    if core == base_filename:
                        # 当前节次的原始文件，只标记为单节存在，不视为合并结果
                        continue
                    # 与 base_filename 同样结构：<prefix>第X(|-Y)节
                    m2 = range_pattern.match(core)
                    if not m2:
                        continue
                    if m2.group("prefix") != prefix:
                        # 日期/周/星期不同，忽略
                        continue
                    candidates.append((f, m2))

            for f, m2 in candidates:
                try:
                    f_start = int(m2.group("start"))
                    f_end = int(m2.group("end") or m2.group("start"))
                    # 只要当前节次区间完全被文件区间覆盖即可判定已存在
                    if f_start <= cur_start and f_end >= cur_end and verify_file_integrity(str(f)):
                        merged_exists = True
                        break
                    # 兼容用户需求：如果当前是单节 (7) 允许被 (6-7) 或 (7-8) 覆盖
                    if cur_start == cur_end and verify_file_integrity(str(f)):
                        if (f_start == cur_start - 1 and f_end == cur_end) or (
                            f_start == cur_start and f_end == cur_end + 1
                        ):
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
            video_url (str): 视频下载 URL
            track_type (str): 视频类型标识('pptVideo'或'teacherTrack')
            row (list): 包含视频时间信息的行数据

        返回:
            dict: 处理结果 {'downloaded': bool, 'merged': bool, 'skipped': bool, 'failed': bool}
        """
        result = {"downloaded": False, "merged": False, "skipped": False, "failed": False}

        # 验证 URL
        if not video_url or not isinstance(video_url, str):
            logger.debug(f"跳过空 URL: {track_type}")
            result["skipped"] = True
            return result

        if not is_valid_url(video_url):
            logger.warning(f"URL 格式可能无效: {video_url}")

        # 获取文件名组件
        components = get_safe_filename_components(row)
        if not components:
            logger.error(f"无法解析行数据，跳过视频: {track_type}")
            result["failed"] = True
            return result

        month, date, day, jie, days, day_chinese = components

        # 根据 API 版本确定文件扩展名
        file_ext = ".ts" if api_version == "legacy" else ".mp4"

        # 构建基础文件名和完整文件名
        base_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节"
        filename = f"{base_filename}-{track_type}{file_ext}"
        filepath = Path(save_dir) / filename

        # 检查文件是否已存在
        single_exists, merged_exists = check_existing_files(base_filename, track_type, save_dir)

        if merged_exists:
            logger.info(f"合并后的视频已存在，跳过: {filename}")
            result["skipped"] = True
            return result

        if single_exists:
            logger.info(f"文件已存在，跳过下载: {filename}")
            result["skipped"] = True
        else:
            # 根据 API 版本选择下载函数
            logger.info(f"开始下载: {filename}")
            try:
                if api_version == "legacy":
                    # 旧版 API：下载 M3U8 格式
                    download_success = download_m3u8(video_url, filename, save_dir)
                else:
                    # 新版 API：下载 MP4 格式
                    download_success = download_mp4(video_url, filename, save_dir)

                if download_success:
                    result["downloaded"] = True
                    logger.info(f"下载成功: {filename}")
                else:
                    # 使用 WARNING 级别避免打断进度条显示
                    logger.warning(f"下载失败: {filename}")
                    result["failed"] = True
                    return result
            except Exception as e:
                # 使用 WARNING 级别避免打断进度条显示
                logger.warning(f"下载异常: {filename}, 错误: {e}")
                result["failed"] = True
                return result

        # 合并逻辑
        if merge and filepath.exists():
            try:
                merged_result = attempt_video_merge(
                    filepath, track_type, month, date, day_chinese, jie, days, course_code, course_name, year, save_dir
                )
                if merged_result:
                    result["merged"] = True
                    logger.info(f"视频合并成功: {filename}")
            except Exception as e:
                logger.error(f"视频合并失败: {filename}, 错误: {e}")

        return result

    def attempt_video_merge(
        filepath, track_type, month, date, day_chinese, jie, days, course_code, course_name, year, save_dir
    ):
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

            for ext in [".mp4", ".ts"]:
                adjacent_file = (
                    save_path
                    / f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{adjacent_jie}节-{track_type}{ext}"
                )
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
    if video_type in ["both", "ppt"]:
        total_tasks += len(rows)
    if video_type in ["both", "teacher"]:
        total_tasks += len(rows)

    stats["total_videos"] = total_tasks

    with tqdm(total=total_tasks, desc="处理视频", unit="个") as pbar:
        for i, row in enumerate(rows):
            try:
                logger.debug(f"处理第 {i+1}/{len(rows)} 行数据")

                # 处理PPT视频
                if video_type in ["both", "ppt"]:
                    result = process_single_video(row[5], "pptVideo", row)
                    if result["downloaded"]:
                        stats["downloaded"] += 1
                    if result["skipped"]:
                        stats["skipped"] += 1
                    if result["failed"]:
                        stats["failed"] += 1
                    if result["merged"]:
                        stats["merged"] += 1
                    pbar.update(1)

                # 处理教师视频
                if video_type in ["both", "teacher"]:
                    result = process_single_video(row[6], "teacherTrack", row)
                    if result["downloaded"]:
                        stats["downloaded"] += 1
                    if result["skipped"]:
                        stats["skipped"] += 1
                    if result["failed"]:
                        stats["failed"] += 1
                    if result["merged"]:
                        stats["merged"] += 1
                    pbar.update(1)

            except Exception as e:
                logger.error(f"处理第 {i+1} 行数据时出错: {e}")
                stats["failed"] += 1
                pbar.update(1)

    # 输出处理结果
    logger.info("视频处理完成！")
    logger.info(f"统计信息: 总计 {stats['total_videos']} 个视频")
    logger.info(f"  - 新下载: {stats['downloaded']} 个")
    logger.info(f"  - 跳过: {stats['skipped']} 个")
    logger.info(f"  - 失败: {stats['failed']} 个")
    logger.info(f"  - 合并: {stats['merged']} 个")

    if stats["failed"] > 0:
        logger.warning(f"有 {stats['failed']} 个视频处理失败，请检查网络连接或重试")

    return stats


def download_single_video(
    row: List[Any],
    course_code: str,
    course_name: str,
    year: int,
    save_dir: str,
    video_type: str,
) -> bool:
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
        if video_type in ["both", "ppt"] and ppt_video:
            total_count += 1
            filename = (
                f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo.mp4"
            )
            filepath = Path(save_dir) / filename

            if filepath.exists():
                print(f"PPT 视频已存在，跳过下载：{filename}")
                success_count += 1
            else:
                print(f"开始下载 PPT 视频：{filename}")
                if download_mp4(ppt_video, filename, save_dir):
                    success_count += 1
                    print(f"PPT 视频下载成功：{filename}")
                else:
                    print(f"PPT 视频下载失败：{filename}")

        # 下载教师视频
        if video_type in ["both", "teacher"] and teacher_track:
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


def download_course_videos(
    live_id: Union[int, str],
    single: int = 0,
    merge: bool = True,
    video_type: str = "both",
    skip_weeks: set = None,
) -> bool:
    """
    下载指定课程的视频，这是核心的下载逻辑函数。

    参数:
        live_id: 课程直播 ID
        single: 下载模式 (0=全部, 1=单节课, 2=半节课)
        merge: 是否自动合并相邻节次视频
        video_type: 视频类型 ('both', 'ppt', 'teacher')
        skip_weeks: 要跳过的周数集合 (如 {1, 2, 3, 7, 9, 10, 11})

    返回:
        bool: 处理是否成功
    """
    if skip_weeks is None:
        skip_weeks = set()
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
            print("1. 课程 ID 是否正确")
            print("2. 网络连接是否正常")
            print("3. 是否已正确配置认证信息")
            return False

        # 检查是否获取到有效数据
        if not data:
            clear_overwrite_line()
            print(f"\n没有找到课程 {live_id} 的数据，请检查课程 ID 是否正确")
            return False

        clear_overwrite_line()
        print(f"成功获取到 {len(data)} 条课程记录")

        # 检测API版本
        from api import detect_api_version

        api_version = detect_api_version(data)
        if api_version == "legacy":
            logger.info(f"检测到旧版课程（2024 及以前），将使用 m3u8 格式下载")
        else:
            logger.info(f"检测到新版课程（2025 及之后），将使用 mp4 格式下载")

        # 处理不同的下载模式
        if single:
            original_data = data[:]
            # 筛选出指定 liveId 的条目（谨慎处理类型差异：entry['id'] 可能为 int，而 live_id 可能为 str）
            live_id_str = str(live_id)
            data = [entry for entry in original_data if str(entry.get("id", "")) == live_id_str]

            if not data:
                logger.error(f"没有找到课程 ID {live_id} 对应的课程记录")
                print(f"错误：没有找到课程 ID {live_id} 对应的课程记录")
                return False

            if single == 1:
                # 单节课模式：下载同一天的所有课程（根据第一个匹配条目的日期/月进行过滤）
                start_time = data[0].get("startTime", {})
                data = [
                    entry
                    for entry in original_data
                    if (
                        entry.get("startTime", {}).get("date") == start_time.get("date")
                        and entry.get("startTime", {}).get("month") == start_time.get("month")
                    )
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
        failed_entries = []  # 收集获取失败的课程条目
        lock = Lock()

        # 只处理已结束的课程
        valid_entries = [entry for entry in data if entry.get("endTime", {}).get("time", 0) / 1000 <= time.time()]

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
                # 提交所有任务，同时保存 entry 和 future 的对应关系
                future_to_entry = {
                    executor.submit(fetch_video_links, entry, lock, desc, api_version): entry
                    for entry in valid_entries
                }

                # 收集所有线程的结果
                for future in concurrent.futures.as_completed(future_to_entry):
                    entry = future_to_entry[future]
                    try:
                        row = future.result()
                        if row:
                            rows.append(row)
                        else:
                            # 获取失败，记录失败的课程条目
                            failed_entries.append(entry)
                    except Exception as e:
                        logger.error(f"获取视频链接时出错: {e}")
                        failed_entries.append(entry)

        if not rows:
            print("没有成功获取到任何视频链接")
            return False

        # 按时间排序：月、日、星期、节次、周数
        rows.sort(key=lambda x: (x[0], x[1], x[2], int(x[3]), x[4]))

        # 根据 skip_weeks 参数过滤掉指定周数的视频
        if skip_weeks:
            original_count = len(rows)
            rows = [row for row in rows if int(row[4]) not in skip_weeks]
            filtered_count = original_count - len(rows)
            if filtered_count > 0:
                skip_list = sorted(list(skip_weeks))
                if len(skip_list) <= 10:
                    print(f"根据设置跳过了第 {', '.join(map(str, skip_list))} 周的 {filtered_count} 个视频")
                else:
                    print(f"根据设置跳过了 {len(skip_list)} 个周的 {filtered_count} 个视频")

        # 保存视频信息到 CSV 文件（保存到 logs/ 目录以便集中管理日志/元数据）
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            csv_filename = logs_dir / f"{save_dir}.csv"
            with open(csv_filename, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["month", "date", "day", "jie", "days", "pptVideo", "teacherTrack"])
                writer.writerows(rows)
            print(f"视频信息已保存到：{csv_filename}")
            logger.info(f"视频信息 CSV 已保存: {csv_filename}")
        except Exception as e:
            logger.warning(f"保存 CSV 文件失败: {e}")

        # 如果有获取失败的课程，集中显示失败信息
        if failed_entries:
            print(f"\n警告：有 {len(failed_entries)} 节课程的视频链接获取失败：")
            for entry in failed_entries:
                try:
                    # 提取课程信息
                    live_id = entry.get("id", "未知")
                    days = entry.get("days", "未知")
                    jie = entry.get("jie", "未知")
                    start_time = entry.get("startTime", {})
                    day = start_time.get("day", 0) if isinstance(start_time, dict) else 0

                    # 转换星期为中文
                    try:
                        day_chinese = day_to_chinese(day)
                    except (ValueError, TypeError):
                        day_chinese = f"星期{day}"

                    # 输出失败信息
                    print(f"  - 第 {days} 周 {day_chinese} 第 {jie} 节 (课程 ID: {live_id})")
                except Exception as e:
                    logger.warning(f"格式化失败课程信息时出错: {e}")
                    print(f"  - 课程 ID: {entry.get('id', '未知')}")
            print("建议：检查录直播平台网页能否播放，如果可以，请向开发者反馈此问题。")
            logger.warning(f"共有 {len(failed_entries)} 节课程获取视频链接失败")

        # 根据下载模式执行不同的下载逻辑
        if single == 1:
            # 单节课模式：最多下载 2 个条目（上下半节课）
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
                stats = process_rows(download_rows, course_code, course_name, year, save_dir, merge, video_type, api_version)

                print(f"\n下载任务完成！")
                print(
                    f"总计 {stats['total_videos']} 个 | 下载 {stats['downloaded']} 个 | 跳过 {stats['skipped']} 个 | 失败 {stats['failed']} 个 | 合并 {stats['merged']} 个"
                )

                if stats["failed"] > 0:
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


def process_all_courses(config: configparser.ConfigParser, video_type: str = "both") -> bool:
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
        if section.get("download", "yes").lower() != "yes":
            continue

        live_id = section.get("live_id")
        course_code = section.get("course_code", "Unknown")
        course_name = section.get("course_name", "Unknown")

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


def parse_m3u8_playlist(m3u8_content: str, base_url: str) -> List[str]:
    """
    解析 M3U8 播放列表，提取 TS 分片的 URL 列表。

    参数:
        m3u8_content (str): M3U8 文件的内容
        base_url (str): M3U8 文件的基础 URL，用于构建完整的分片 URL

    返回:
        List[str]: TS 分片的完整 URL 列表
    """
    segment_urls = []
    lines = m3u8_content.strip().split("\n")

    # 提取 base_url 的目录部分（去掉文件名）
    # 对于特殊的 URL 格式（如包含 cloud://），不使用 urljoin，而是直接字符串拼接
    if "/" in base_url:
        base_dir = base_url.rsplit("/", 1)[0] + "/"
    else:
        base_dir = base_url

    for line in lines:
        line = line.strip()
        # 跳过注释行和空行
        if not line or line.startswith("#"):
            continue

        # 构建完整的 URL
        if line.startswith("http://") or line.startswith("https://"):
            # 已经是完整 URL
            segment_urls.append(line)
        else:
            # 相对 URL，需要拼接
            # 不使用 urljoin，因为它对特殊 URL 格式（如 cloud://）处理不当
            # 直接进行字符串拼接
            segment_urls.append(base_dir + line)

    logger.debug(f"从 M3U8 播放列表中解析出 {len(segment_urls)} 个 TS 分片")
    return segment_urls


def download_m3u8_segment(url: str, segment_index: int, auth_cookies: Dict[str, str]) -> Optional[bytes]:
    """
    下载单个 M3U8 TS 分片。

    参数:
        url (str): TS 分片的 URL
        segment_index (int): 分片索引（用于日志）
        auth_cookies (Dict[str, str]): 认证 cookies

    返回:
        Optional[bytes]: 分片的二进制数据，失败时返回 None
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cookie": format_auth_cookies(auth_cookies),
        "Referer": "http://newesxidian.chaoxing.com/",
    }

    max_retries = 10
    for attempt in range(max_retries):
        try:
            logger.debug(f"下载 TS 分片 {segment_index}: {url}")
            response = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            return response.content
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"下载 TS 分片 {segment_index} 失败（尝试 {attempt + 1}/{max_retries}）: {e}")
                time.sleep(1)
            else:
                logger.warning(f"下载 TS 分片 {segment_index} 最终失败: {e}")
                return None
    return None


def download_m3u8(
    m3u8_url: str,
    filename: str,
    save_dir: str,
    max_attempts: int = MAX_DOWNLOAD_RETRIES,
) -> bool:
    """
    下载M3U8视频文件，自动解析播放列表并下载所有 TS 分片，最后合并为完整视频。

    参数:
        m3u8_url (str): M3U8 播放列表的 URL
        filename (str): 保存的文件名（.ts格式）
        save_dir (str): 保存目录
        max_attempts (int): 最大重试次数

    返回:
        bool: 下载是否成功
    """
    # 参数验证
    if not m3u8_url or not isinstance(m3u8_url, str):
        raise ValueError("M3U8 URL 不能为空且必须是字符串类型")

    if not is_valid_url(m3u8_url):
        logger.warning(f"M3U8 URL 格式可能无效: {m3u8_url}")

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

    # 获取认证信息
    try:
        auth_cookies = get_auth_cookies(FID)
    except Exception as e:
        logger.error(f"获取认证信息失败: {e}")
        raise ValueError(f"无法获取认证信息: {e}")

    # 重试下载机制
    for attempt in range(max_attempts):
        temp_path = None
        try:
            logger.info(f"开始下载 M3U8 视频 ({attempt + 1}/{max_attempts}): {safe_filename}")

            # 1. 下载 M3U8 播放列表
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cookie": format_auth_cookies(auth_cookies),
            }

            logger.debug(f"GET {m3u8_url}")
            m3u8_response = requests.get(m3u8_url, headers=headers, timeout=REQUEST_TIMEOUT)
            m3u8_response.raise_for_status()
            m3u8_content = m3u8_response.text

            # 2. 解析 M3U8 播放列表
            segment_urls = parse_m3u8_playlist(m3u8_content, m3u8_url)

            if not segment_urls:
                raise ValueError("M3U8 播放列表中没有找到 TS 分片")

            logger.info(f"M3U8 播放列表包含 {len(segment_urls)} 个 TS 分片")

            # 3. 创建临时文件
            temp_path = output_path.with_suffix(".tmp")

            # 4. 下载所有 TS 分片并写入临时文件
            downloaded_segments = 0
            failed_segments = []

            with open(temp_path, "wb") as f:
                with tqdm(total=len(segment_urls), desc=safe_filename, unit="片段", leave=False) as pbar:
                    # 使用多线程下载分片
                    max_workers = min(8, len(segment_urls))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        # 提交所有下载任务
                        future_to_index = {
                            executor.submit(download_m3u8_segment, url, idx, auth_cookies): idx
                            for idx, url in enumerate(segment_urls)
                        }

                        # 按顺序收集结果
                        segments_data = [None] * len(segment_urls)
                        for future in concurrent.futures.as_completed(future_to_index):
                            idx = future_to_index[future]
                            try:
                                segment_data = future.result()
                                if segment_data:
                                    segments_data[idx] = segment_data
                                    downloaded_segments += 1
                                else:
                                    failed_segments.append(idx)
                            except Exception as e:
                                logger.error(f"下载 TS 分片 {idx} 时出错: {e}")
                                failed_segments.append(idx)
                            pbar.update(1)

                    # 按顺序写入分片
                    for idx, segment_data in enumerate(segments_data):
                        if segment_data:
                            f.write(segment_data)
                        else:
                            logger.warning(f"TS 分片 {idx} 缺失，可能导致视频不完整")

            # 5. 检查下载完整性
            if failed_segments:
                logger.warning(
                    f"有 {len(failed_segments)} 个 TS 分片下载失败（共 {len(segment_urls)} 个），视频可能不完整"
                )
                # 如果失败分片超过 20%，认为下载失败
                if len(failed_segments) / len(segment_urls) > 0.2:
                    raise ValueError(f"失败分片过多 ({len(failed_segments)}/{len(segment_urls)})")

            # 6. 验证下载的文件
            if not verify_file_integrity(str(temp_path)):
                raise ValueError("下载的 M3U8 视频文件验证失败")

            # 7. 原子性重命名
            shutil.move(str(temp_path), str(output_path))
            logger.info(
                f"M3U8 视频下载完成: {safe_filename} ({format_file_size(output_path.stat().st_size)})，成功下载 {downloaded_segments}/{len(segment_urls)} 个分片"
            )
            return True

        except requests.Timeout:
            error_msg = f"下载 M3U8 超时 ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(Exception("下载超时"), f"下载 M3U8 {safe_filename} 失败", level=logging.WARNING)

        except requests.ConnectionError:
            error_msg = f"网络连接错误 ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(Exception("网络连接失败"), f"下载 M3U8 {safe_filename} 失败", level=logging.WARNING)

        except requests.HTTPError as e:
            error_msg = f"HTTP 错误 {e.response.status_code} ({attempt + 1}/{max_attempts}): {safe_filename}"
            logger.warning(error_msg)
            if e.response.status_code in [404, 403, 410]:
                # 对于客户端错误，不需要重试
                handle_exception(e, f"下载 M3U8 {safe_filename} 失败：资源不可用", level=logging.WARNING)
                break
            if attempt == max_attempts - 1:
                handle_exception(e, f"下载 M3U8 {safe_filename} 失败", level=logging.WARNING)

        except Exception as e:
            error_msg = f"下载 M3U8 失败 ({attempt + 1}/{max_attempts}): {safe_filename}, 错误: {e}"
            logger.warning(error_msg)
            if attempt == max_attempts - 1:
                handle_exception(e, f"下载 M3U8 {safe_filename} 最终失败", level=logging.WARNING)

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
