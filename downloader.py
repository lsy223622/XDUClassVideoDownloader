#!/usr/bin/env python3
"""
下载模块
负责MP4视频文件的下载和视频文件的合并处理
支持跨平台的视频下载和智能合并相邻节次的视频
"""

import subprocess
import os
import re
import requests
import shutil
from tqdm import tqdm
from utils import day_to_chinese, handle_exception, get_auth_cookies, format_auth_cookies
from api import FID


def download_mp4(url, filename, save_dir, max_attempts=2):
    """
    下载MP4视频文件。

    参数:
        url (str): MP4视频文件的URL
        filename (str): 保存的文件名
        save_dir (str): 保存目录
        max_attempts (int): 最大重试次数，默认2次
    """
    if not url:
        print(f"跳过下载 {filename}：URL为空")
        return

    # 构建完整的文件路径
    output_path = os.path.join(save_dir, filename)

    # 检查文件是否已存在
    if os.path.exists(output_path):
        print(f"文件已存在，跳过下载：{filename}")
        return

    # 获取认证头（将 FID 由 api 层提供）
    auth_cookies = get_auth_cookies(FID)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "video/mp4,video/*,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cookie": format_auth_cookies(auth_cookies),
        "Referer": "http://newes.chaoxing.com/"
    }

    # 重试下载机制
    for attempt in range(max_attempts):
        try:
            print(f"开始下载：{filename}")

            # 发送HEAD请求获取文件大小
            head_response = requests.head(
                url, headers=headers, allow_redirects=True, timeout=30)
            total_size = int(head_response.headers.get('content-length', 0))

            # 发送GET请求下载文件
            response = requests.get(
                url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()

            # 创建临时文件路径
            temp_path = output_path + '.tmp'

            # 使用进度条下载文件
            with open(temp_path, 'wb') as f:
                if total_size > 0:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    # 如果无法获取文件大小，显示简单进度
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            # 下载完成，重命名临时文件
            shutil.move(temp_path, output_path)
            print(f"下载完成：{filename}")
            break  # 下载成功，跳出重试循环

        except Exception as e:
            # 下载失败，记录错误并重试
            print(f"第 {attempt+1} 次下载 {filename} 出错：{str(e)}")
            # 清理临时文件
            temp_path = output_path + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if attempt == max_attempts - 1:
                # 达到最大重试次数，下载最终失败
                print(f"下载 {filename} 失败。")


def download_m3u8(url, filename, save_dir, command='', max_attempts=2):
    """
    兼容性函数：将M3U8下载调用重定向到MP4下载。

    参数:
        url (str): 视频文件的URL
        filename (str): 保存的文件名
        save_dir (str): 保存目录
        command (str): 自定义下载命令（在新版本中被忽略）
        max_attempts (int): 最大重试次数，默认2次
    """
    # 将.ts扩展名替换为.mp4
    if filename.endswith('.ts'):
        filename = filename[:-3] + '.mp4'

    download_mp4(url, filename, save_dir, max_attempts)


def merge_videos(files, output_file):
    """
    合并多个MP4视频文件为一个文件。
    由于新版本下载的是MP4文件，我们使用FFmpeg进行合并。

    参数:
        files (list): 要合并的视频文件路径列表
        output_file (str): 输出文件路径
    """
    try:
        # 检查是否安装了FFmpeg
        try:
            subprocess.run(['ffmpeg', '-version'],
                           capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("警告：未找到FFmpeg，无法合并视频文件。请安装FFmpeg以启用视频合并功能。")
            return

        # 创建临时文件列表（使用绝对路径，避免相对路径导致的重复目录问题）
        temp_list_file = output_file + '.filelist.txt'
        # 验证所有待合并文件是否存在，收集不存在的文件以便报告
        missing = [p for p in files if not os.path.exists(p)]
        if missing:
            msg = f"合并前检测到以下文件不存在，跳过合并：{missing}"
            handle_exception(FileNotFoundError(msg), msg)
            # 如果存在临时文件（可能残留），尝试删除
            if os.path.exists(temp_list_file):
                try:
                    os.remove(temp_list_file)
                except Exception:
                    pass
            return

        with open(temp_list_file, 'w', encoding='utf-8') as f:
            for file_path in files:
                # 使用绝对路径并将反斜杠转换为正斜杠，FFmpeg on Windows 能正确识别
                abs_path = os.path.abspath(file_path)
                escaped_path = abs_path.replace("'", r"\'").replace("\\", "/")
                f.write(f"file '{escaped_path}'\n")

        # 使用FFmpeg合并视频
        command = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', temp_list_file,
            '-c', 'copy',  # 直接复制，不重新编码
            '-y',  # 覆盖输出文件
            output_file
        ]

        subprocess.run(command, check=True, capture_output=True)
        print(f"合并完成：{output_file}")

        # 合并成功后删除原始文件和临时文件
        for file in files:
            if os.path.exists(file):
                os.remove(file)

        if os.path.exists(temp_list_file):
            os.remove(temp_list_file)

    except subprocess.CalledProcessError as e:
        # 合并失败时记录错误信息
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        handle_exception(e, f"合并 {output_file} 失败: {error_msg}")

        # 清理临时文件
        temp_list_file = output_file + '.filelist.txt'
        if os.path.exists(temp_list_file):
            os.remove(temp_list_file)
    except Exception as e:
        handle_exception(e, f"合并 {output_file} 时发生未知错误")


def process_rows(rows, course_code, course_name, year, save_dir, command='', merge=True, video_type='both'):
    """
    处理视频行数据，下载视频并可选择性地合并相邻节次的视频。

    参数:
        rows (list): 视频信息行列表，每行包含[月, 日, 星期, 节次, 周数, ppt_video_url, teacher_track_url]
        course_code (str): 课程代码
        course_name (str): 课程名称
        year (int): 年份
        save_dir (str): 保存目录
        command (str): 自定义下载命令（新版本中被忽略）
        merge (bool): 是否自动合并相邻节次的视频
        video_type (str): 视频类型('both', 'ppt', 'teacher')
    """
    def process_video(video_url, track_type, row):
        """
        处理单个视频的下载和合并逻辑。

        参数:
            video_url (str): 视频下载URL
            track_type (str): 视频类型标识('pptVideo'或'teacherTrack')
            row (list): 包含视频时间信息的行数据
        """
        # 如果视频URL为空，跳过处理
        if not video_url:
            return

        # 解析行数据获取时间信息
        month, date, day, jie, days = row[:5]
        jie = int(jie)  # 确保 jie 是整数
        day_chinese = day_to_chinese(day)  # 转换星期数字为中文

        # 构建文件名：课程代码+课程名+年月日+周次+星期+节次+视频类型 (使用.mp4扩展名)
        filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-{track_type}.mp4"
        filepath = os.path.join(save_dir, filename)

        # 检查是否存在包括本节的合并后文件，避免重复下载
        merged_exists = any([
            os.path.exists(os.path.join(
                save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}-{jie}节-{track_type}.mp4")),
            os.path.exists(os.path.join(
                save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie+1}节-{track_type}.mp4")),
            # 也检查.ts扩展名的合并文件（向后兼容）
            os.path.exists(os.path.join(
                save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}-{jie}节-{track_type}.ts")),
            os.path.exists(os.path.join(
                save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie+1}节-{track_type}.ts"))
        ])
        if merged_exists:
            print(f"合并后的视频已存在，跳过下载和合并：{filename}")
            return

        # 检查单个文件是否已存在（包括.ts和.mp4两种格式）
        ts_filepath = filepath.replace('.mp4', '.ts')
        if os.path.exists(filepath) or os.path.exists(ts_filepath):
            print(f"文件已存在，跳过下载：{filename}")
        else:
            # 文件不存在，开始下载（使用新的MP4下载函数）
            download_mp4(video_url, filename, save_dir)

        # 合并逻辑部分
        if not os.path.exists(filepath):
            print(f"文件不存在，跳过合并：{filename}")
            return

        # 如果禁用合并功能，直接返回
        if not merge:
            return

        # 检查是否存在相邻节次的视频文件（前一节或后一节）
        prev_filepath_mp4 = os.path.join(
            save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}节-{track_type}.mp4")
        next_filepath_mp4 = os.path.join(
            save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie+1}节-{track_type}.mp4")

        # 也检查.ts格式的文件（向后兼容）
        prev_filepath_ts = os.path.join(
            save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}节-{track_type}.ts")
        next_filepath_ts = os.path.join(
            save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie+1}节-{track_type}.ts")

        # 收集需要合并的文件
        files_to_merge = []
        if os.path.exists(prev_filepath_mp4):
            files_to_merge.append(prev_filepath_mp4)
        elif os.path.exists(prev_filepath_ts):
            files_to_merge.append(prev_filepath_ts)

        if os.path.exists(next_filepath_mp4):
            files_to_merge.append(next_filepath_mp4)
        elif os.path.exists(next_filepath_ts):
            files_to_merge.append(next_filepath_ts)

        # 如果找到相邻文件，进行合并
        if files_to_merge:
            files_to_merge.append(filepath)  # 添加当前文件
            # 按节次排序确保合并顺序正确
            files_to_merge.sort(key=lambda f: int(
                re.search(r"第(\d+)节", f).group(1)))

            # 构建合并后的文件名，包含节次范围
            merged_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1 if any('第{}节'.format(jie-1) in f for f in files_to_merge) else jie}-{jie+1 if any('第{}节'.format(jie+1) in f for f in files_to_merge) else jie}节-{track_type}.mp4"
            merged_filepath = os.path.join(save_dir, merged_filename)
            # 执行视频合并
            merge_videos(files_to_merge, merged_filepath)

    # 根据视频类型设置，处理不同类型的视频
    for row in rows:
        if video_type in ['both', 'ppt']:
            # 处理PPT视频（索引5是pptVideo URL）
            process_video(row[5], 'pptVideo', row)
        if video_type in ['both', 'teacher']:
            # 处理教师视频（索引6是teacherTrack URL）
            process_video(row[6], 'teacherTrack', row)
