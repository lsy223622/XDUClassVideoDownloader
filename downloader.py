#!/usr/bin/env python3

import subprocess
import sys
import os
import traceback
from utils import day_to_chinese

def download_m3u8(url, filename, save_dir, command=''):
    if not command:
        if sys.platform.startswith('win32'):
            command = f'vsd-upx.exe save {url} -o {save_dir}\{filename} --retry-count 32 -t 16'
        else:
            command = f'./vsd-upx save {url} -o {save_dir}/{filename} --retry-count 32 -t 16'
    else:
        command = command.format(url=url, filename=filename, save_dir=save_dir)

    MAX_ATTEMPTS = 2

    for attempt in range(MAX_ATTEMPTS):
        try:
            subprocess.run(command, shell=True, check=True)
            break
        except subprocess.CalledProcessError:
            print(f"第 {attempt+1} 次下载 {filename} 出错：\n{traceback.format_exc()}\n重试中...")
            if attempt == MAX_ATTEMPTS - 1:
                print(f"下载 {filename} 失败。")

def merge_videos(files, output_file):
    if sys.platform.startswith('win32'):
        command = f'vsd-upx.exe merge -o {output_file} {" ".join(files)}'
    else:
        command = f'./vsd-upx merge -o {output_file} {" ".join(files)}'

    try:
        subprocess.run(command, shell=True, check=True)
        print(f"合并完成：{output_file}")
        for file in files:
            if os.path.exists(file):
                os.remove(file)
    except subprocess.CalledProcessError:
        print(f"合并 {output_file} 失败：\n{traceback.format_exc()}")

def process_rows(rows, course_code, course_name, year, save_dir, command='', merge=True):
    def process_video(video_url, track_type, row, row_next=None):
        if not video_url:
            return None
        
        month, date, day, jie, days = row[:5]
        day_chinese = day_to_chinese(day)
        filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-{track_type}.ts"
        filepath = os.path.join(save_dir, filename)
        
        if not os.path.exists(filepath):
            download_m3u8(video_url, filename, save_dir, command=command)
        
        if row_next:
            month_next, date_next, day_next, jie_next, days_next = row_next[:5] 
            day_chinese_next = day_to_chinese(day_next)
            filename_next = f"{course_code}{course_name}{year}年{month_next}月{date_next}日第{days_next}周星期{day_chinese_next}第{jie_next}节-{track_type}.ts"
            filepath_next = os.path.join(save_dir, filename_next)
            if not os.path.exists(filepath_next):
                download_m3u8(row_next[5 if track_type == 'pptVideo' else 6], filename_next, save_dir, command=command)
            
            if merge:
                merged_filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}-{jie_next}节-{track_type}.ts"
                merged_filepath = os.path.join(save_dir, merged_filename)
                
                # 检查文件是否存在
                if os.path.exists(filepath) and os.path.exists(filepath_next):
                    merge_videos([filepath, filepath_next], merged_filepath)
                else:
                    print(f"合并文件失败，文件不存在: {filepath} 或 {filepath_next}")
        
        return filepath

    for i in range(0, len(rows), 2):
        row1 = rows[i]
        row2 = rows[i + 1] if i + 1 < len(rows) else None
        
        ppt_video1 = process_video(row1[5], 'pptVideo', row1, row2) 
        teacher_track1 = process_video(row1[6], 'teacherTrack', row1, row2)