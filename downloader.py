#!/usr/bin/env python3
"""
下载模块
负责M3U8视频流的下载和视频文件的合并处理
支持跨平台的视频下载和智能合并相邻节次的视频
"""

import subprocess
import sys
import os
import traceback
import re
from shlex import quote
from utils import day_to_chinese, handle_exception

def download_m3u8(url, filename, save_dir, command='', max_attempts=2):
    """
    下载M3U8视频流文件。
    
    参数:
        url (str): M3U8视频流的URL
        filename (str): 保存的文件名
        save_dir (str): 保存目录
        command (str): 自定义下载命令，为空时使用默认命令
        max_attempts (int): 最大重试次数，默认2次
    """
    # 如果没有提供自定义命令，使用默认的vsd-upx下载器
    if not command:
        # 根据操作系统选择相应的可执行文件
        if sys.platform.startswith('win32'):
            # Windows系统使用exe文件
            output_path = os.path.join(save_dir, filename)
            command = f'vsd-upx.exe save {url} -o "{output_path}" --retry-count 32 -t 16'
        else:
            # Linux/macOS系统使用可执行文件
            output_path = os.path.join(save_dir, filename)
            safe_path = quote(output_path)  # 转义路径以防特殊字符
            command = f'./vsd-upx save {url} -o {safe_path} --retry-count 32 -t 16'
    else:
        # 使用用户提供的自定义命令，替换占位符
        command = command.format(url=url, filename=filename, save_dir=save_dir)

    # 重试下载机制
    for attempt in range(max_attempts):
        try:
            # 执行下载命令
            subprocess.run(command, shell=True, check=True)
            break  # 下载成功，跳出重试循环
        except subprocess.CalledProcessError:
            # 下载失败，记录错误并重试
            print(f"第 {attempt+1} 次下载 {filename} 出错：\n{traceback.format_exc()}\n重试中...")
            if attempt == max_attempts - 1:
                # 达到最大重试次数，下载最终失败
                print(f"下载 {filename} 失败。")

def merge_videos(files, output_file):
    """
    合并多个视频文件为一个文件。
    
    参数:
        files (list): 要合并的视频文件路径列表
        output_file (str): 输出文件路径
    """
    # 根据操作系统构建不同的合并命令
    if sys.platform.startswith('win32'):
        # Windows系统：使用双引号包围文件路径
        files_str = ' '.join(f'"{f}"' for f in files)
        command = f'vsd-upx.exe merge -o "{output_file}" {files_str}'
    else:
        # Linux/macOS系统：使用quote函数转义特殊字符
        safe_output = quote(output_file)
        safe_files = ' '.join(quote(f) for f in files)
        command = f'./vsd-upx merge -o {safe_output} {safe_files}'

    try:
        # 执行合并命令
        subprocess.run(command, shell=True, check=True)
        print(f"合并完成：{output_file}")
        
        # 合并成功后删除原始文件以节省空间
        for file in files:
            if os.path.exists(file):
                os.remove(file)
    except subprocess.CalledProcessError as e:
        # 合并失败时记录错误信息
        handle_exception(e, f"合并 {output_file} 失败")

def process_rows(rows, course_code, course_name, year, save_dir, command='', merge=True, video_type='both'):
    """
    处理视频行数据，下载视频并可选择性地合并相邻节次的视频。
    
    参数:
        rows (list): 视频信息行列表，每行包含[月, 日, 星期, 节次, 周数, ppt_video_url, teacher_track_url]
        course_code (str): 课程代码
        course_name (str): 课程名称
        year (int): 年份
        save_dir (str): 保存目录
        command (str): 自定义下载命令
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
        
        # 构建文件名：课程代码+课程名+年月日+周次+星期+节次+视频类型
        filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-{track_type}.ts"
        filepath = os.path.join(save_dir, filename)
        
        # 检查是否存在包括本节的合并后文件，避免重复下载
        merged_exists = any([
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}-{jie}节-{track_type}.ts")),
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}-{jie}节-{track_type}.mp4")),
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie+1}节-{track_type}.ts")),
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie+1}节-{track_type}.mp4"))
        ])
        if merged_exists:
            print(f"合并后的视频已存在，跳过下载和合并：{filename}")
            return
        
        # 检查单个文件是否已存在
        if os.path.exists(filepath):
            print(f"文件已存在，跳过下载：{filename}")
        else:
            # 文件不存在，开始下载
            download_m3u8(video_url, filename, save_dir, command=command)
        
        # 合并逻辑部分
        if not os.path.exists(filepath):
            print(f"文件不存在，跳过合并：{filename}")
            return
        
        # 如果禁用合并功能，直接返回
        if not merge:
            return

        # 检查是否存在相邻节次的视频文件（前一节或后一节）
        prev_filepath = os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}节-{track_type}.ts")
        next_filepath = os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie+1}节-{track_type}.ts")
        
        # 收集需要合并的文件
        files_to_merge = []
        if os.path.exists(prev_filepath):
            files_to_merge.append(prev_filepath)
        if os.path.exists(next_filepath):
            files_to_merge.append(next_filepath)
            
        # 如果找到相邻文件且都是ts格式，进行合并
        if files_to_merge and all(f.endswith('.ts') for f in files_to_merge):
            files_to_merge.append(filepath)  # 添加当前文件
            # 按节次排序确保合并顺序正确
            files_to_merge.sort(key=lambda f: int(re.search(r"第(\d+)节", f).group(1)))
            
            # 构建合并后的文件名，包含节次范围
            merged_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1 if os.path.exists(prev_filepath) else jie}-{jie+1 if os.path.exists(next_filepath) else jie}节-{track_type}.ts"
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
