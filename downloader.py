#!/usr/bin/env python3

import subprocess
import sys
import os
import traceback

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
