#!/usr/bin/env python3

import subprocess
import sys
import os
import traceback
import re
from shlex import quote
from utils import day_to_chinese, handle_exception

def download_m3u8(url, filename, save_dir, command='', max_attempts=2):
    if not command:
        if sys.platform.startswith('win32'):
            output_path = os.path.join(save_dir, filename)
            command = f'vsd-upx.exe save {url} -o "{output_path}" --retry-count 32 -t 16'
        else:
            output_path = os.path.join(save_dir, filename)
            safe_path = quote(output_path)
            command = f'./vsd-upx save {url} -o {safe_path} --retry-count 32 -t 16'
    else:
        command = command.format(url=url, filename=filename, save_dir=save_dir)

    for attempt in range(max_attempts):
        try:
            subprocess.run(command, shell=True, check=True)
            break
        except subprocess.CalledProcessError:
            print(f"第 {attempt+1} 次下载 {filename} 出错：\n{traceback.format_exc()}\n重试中...")
            if attempt == max_attempts - 1:
                print(f"下载 {filename} 失败。")

def merge_videos(files, output_file):
    if sys.platform.startswith('win32'):
        files_str = ' '.join(f'"{f}"' for f in files)
        command = f'vsd-upx.exe merge -o "{output_file}" {files_str}'
    else:
        safe_output = quote(output_file)
        safe_files = ' '.join(quote(f) for f in files)
        command = f'./vsd-upx merge -o {safe_output} {safe_files}'

    try:
        subprocess.run(command, shell=True, check=True)
        print(f"合并完成：{output_file}")
        for file in files:
            if os.path.exists(file):
                os.remove(file)
    except subprocess.CalledProcessError as e:
        handle_exception(e, f"合并 {output_file} 失败")

def process_rows(rows, course_code, course_name, year, save_dir, command='', merge=True, video_type='both'):
    def process_video(video_url, track_type, row):
        if not video_url:
            return
        
        month, date, day, jie, days = row[:5]
        jie = int(jie)  # 确保 jie 是整数
        day_chinese = day_to_chinese(day)
        filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-{track_type}.ts"
        filepath = os.path.join(save_dir, filename)
        
        # 检查是否存在包括本节的合并后文件
        merged_exists = any([
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}-{jie}节-{track_type}.ts")),
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}-{jie}节-{track_type}.mp4")),
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie+1}节-{track_type}.ts")),
            os.path.exists(os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie+1}节-{track_type}.mp4"))
        ])
        if merged_exists:
            print(f"合并后的视频已存在，跳过下载和合并：{filename}")
            return
        
        # 检查是否存在和待下载的文件名相同的文件
        if os.path.exists(filepath):
            print(f"文件已存在，跳过下载：{filename}")
        else:
            download_m3u8(video_url, filename, save_dir, command=command)
        
        # 合并部分
        if not os.path.exists(filepath):
            print(f"文件不存在，跳过合并：{filename}")
            return
        
        # 如果 merge 为 False，跳过合并逻辑
        if not merge:
            return

        # 检查是否存在和当前文件名相同但是 jie 少 1 或者多 1 的文件
        prev_filepath = os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1}节-{track_type}.ts")
        next_filepath = os.path.join(save_dir, f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie+1}节-{track_type}.ts")
        
        files_to_merge = []
        if os.path.exists(prev_filepath):
            files_to_merge.append(prev_filepath)
        if os.path.exists(next_filepath):
            files_to_merge.append(next_filepath)
            
        if files_to_merge and all(f.endswith('.ts') for f in files_to_merge):
            files_to_merge.append(filepath)
            files_to_merge.sort(key=lambda f: int(re.search(r"第(\d+)节", f).group(1)))  # 确保合并顺序正确
            merged_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie-1 if os.path.exists(prev_filepath) else jie}-{jie+1 if os.path.exists(next_filepath) else jie}节-{track_type}.ts"
            merged_filepath = os.path.join(save_dir, merged_filename)
            merge_videos(files_to_merge, merged_filepath)
        
    for row in rows:
        if video_type in ['both', 'ppt']:
            process_video(row[5], 'pptVideo', row)
        if video_type in ['both', 'teacher']:
            process_video(row[6], 'teacherTrack', row)
