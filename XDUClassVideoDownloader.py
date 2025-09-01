#!/usr/bin/env python3
"""
西安电子科技大学录直播平台课程视频下载器 - 主程序
用于下载单门课程的所有视频或指定视频
"""
import os
import csv
import time
import traceback
from tqdm import tqdm
from argparse import ArgumentParser
from api import get_initial_data, get_m3u8_links, check_update, fetch_m3u8_links
from downloader import download_m3u8, process_rows
from utils import day_to_chinese, user_input_with_check, create_directory, handle_exception, remove_invalid_chars, calculate_optimal_threads
import concurrent.futures
from threading import Lock

# 程序启动时检查更新
check_update()

def main(liveid=None, command='', single=0, merge=True, video_type='both'):
    """
    主函数：下载指定课程的视频。
    
    参数:
        liveid (int): 课程直播ID，为None时进入交互模式
        command (str): 自定义下载命令
        single (int): 下载模式 (0=全部, 1=单节课, 2=半节课)
        merge (bool): 是否自动合并相邻节次视频
        video_type (str): 视频类型 ('both', 'ppt', 'teacher')
    """
    # 交互模式：用户输入参数
    if not liveid:
        # 获取课程ID
        liveid = int(user_input_with_check("请输入 liveId：", lambda x: x.isdigit() and len(x) <= 10))
        
        # 选择下载模式
        single = user_input_with_check("是否仅下载单节课视频？输入 y 下载单节课，n 下载这门课所有视频，s 则仅下载单集（半节课）视频，直接回车默认单节课 (Y/n/s):", lambda x: x.lower() in ['', 'y', 'n', 's']).lower()
        single = 1 if single in ['', 'y'] else 2 if single == 's' else 0
        
        # 选择是否合并视频
        merge = user_input_with_check("是否自动合并上下半节课视频？(Y/n):", lambda x: x.lower() in ['', 'y', 'n']).lower() != 'n'
        
        # 选择视频类型
        video_type_input = user_input_with_check("选择要下载的视频类型？输入 b 下载两种视频，p 仅下载pptVideo，t 仅下载teacherTrack，直接回车默认两种都下载 (B/p/t):", lambda x: x.lower() in ['', 'b', 'p', 't']).lower()
        video_type = 'ppt' if video_type_input == 'p' else 'teacher' if video_type_input == 't' else 'both'
        
        # 设置跳过周数
        skip_input = user_input_with_check(
            "是否从某个周数才开始下载？输入周数（如 3 则从第三周开始下载）或直接回车表示从第一周开始：",
            lambda x: x.isdigit() or x == ''
        ).strip()
        skip_until = int(skip_input) - 1 if skip_input.isdigit() else 0
        if skip_until < 0:
            raise ValueError("跳过的周数不能为负数")
    else:
        # 非交互模式：使用传入的参数
        liveid = int(liveid) if not isinstance(liveid, int) else liveid
        single = min(single, 2)  # 限制single参数范围
        skip_until = 0  # 非交互模式下，默认不跳过任何周

    try:
        # 获取课程的初始数据
        data = get_initial_data(liveid)
    except Exception as e:
        handle_exception(e, "获取初始数据时发生错误")
        return

    # 检查是否获取到有效数据
    if not data:
        print("没有找到数据，请检查 liveId 是否正确。")
        return

    # 处理不同的下载模式
    if single:
        data_temp = data[:]  # 创建数据副本
        # 筛选出指定liveId的条目
        data = [entry for entry in data_temp if entry["id"] == liveid]
        if not data:
            raise ValueError("No matching entry found for the specified liveId")
        
        if single == 1:
            # 单节课模式：下载同一天的所有课程
            start_time = data[0]["startTime"]
            data = [entry for entry in data_temp if entry["startTime"]["date"] == start_time["date"] and entry["startTime"]["month"] == start_time["month"]]

    # 提取课程基本信息
    first_entry = data[0]
    year = time.gmtime(first_entry["startTime"]["time"] / 1000).tm_year
    course_code = first_entry["courseCode"]
    course_name = remove_invalid_chars(first_entry["courseName"])
    save_dir = f"{year}年{course_code}{course_name}"
    create_directory(save_dir)  # 创建保存目录
    csv_filename = f"{save_dir}.csv"

    # 多线程获取所有视频的M3U8链接
    rows = []
    lock = Lock()  # 线程锁，保护进度条更新
    with tqdm(total=len(data), desc="获取视频链接") as desc:
        # 计算最佳线程数
        max_threads = calculate_optimal_threads()
        print(f"CPU 核心数: {os.cpu_count()}, 最佳线程数: {max_threads}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            # 只处理已结束的课程（endTime <= 当前时间）
            futures = [executor.submit(fetch_m3u8_links, entry, lock, desc) for entry in data if entry["endTime"]["time"] / 1000 <= time.time()]
            # 收集所有线程的结果
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                if row:
                    rows.append(row)

    # 按时间排序：月、日、星期、节次、周数
    rows.sort(key=lambda x: (x[0], x[1], x[2], int(x[3]), x[4]))

    # 根据skip_until参数过滤掉指定周数之前的视频
    if skip_until > 0:
        rows = [row for row in rows if int(row[4]) > skip_until]

    # 将视频信息保存到CSV文件
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        # 写入CSV表头
        writer.writerow(['month', 'date', 'day', 'jie', 'days', 'pptVideo', 'teacherTrack'])
        writer.writerows(rows)

    print(f"{csv_filename} 文件已创建并写入数据。")

    # 根据下载模式执行不同的下载逻辑
    if single == 1:
        # 单节课模式：最多下载2个条目（上下半节课）
        process_rows(rows[:2], course_code, course_name, year, save_dir, command, merge, video_type)
    elif single == 2:
        # 半节课模式：只下载第一个条目
        row = rows[0]
        month, date, day, jie, days, ppt_video, teacher_track = row
        day_chinese = day_to_chinese(day)
        
        # 下载PPT视频
        if video_type in ['both', 'ppt'] and ppt_video:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-pptVideo.ts"
            filepath = os.path.join(save_dir, filename)
            if not os.path.exists(filepath):
                download_m3u8(ppt_video, filename, save_dir, command=command)
        
        # 下载教师视频
        if video_type in ['both', 'teacher'] and teacher_track:
            filename = f"{course_code}{course_name}{year}年{month}月{date}日第{days}周星期{day_chinese}第{jie}节-teacherTrack.ts"
            filepath = os.path.join(save_dir, filename)
            if not os.path.exists(filepath):
                download_m3u8(teacher_track, filename, save_dir, command=command)
    else:
        # 全部下载模式：下载所有视频
        process_rows(rows, course_code, course_name, year, save_dir, command, merge, video_type)

    print("所有视频下载和处理完成。")


def parse_arguments():
    """
    解析命令行参数。
    
    返回:
        argparse.Namespace: 包含所有命令行参数的对象
    """
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('liveid', nargs='?', default=None, help="课程的 liveId，不输入则采用交互式方式获取")
    parser.add_argument('-c', '--command', default='', help="自定义下载命令，使用 {url}, {save_dir}, {filename} 作为替换标记")
    parser.add_argument('-s', '--single', action='count', default=0, help="仅下载单节课视频（-s：单节课视频，-ss：半节课视频）")
    parser.add_argument('--no-merge', action='store_false', help="不合并上下半节课视频")
    parser.add_argument('--video-type', choices=['both', 'ppt', 'teacher'], default=None, help="选择要下载的视频类型：both（两种都下载）、ppt（仅下载pptVideo）、teacher（仅下载teacherTrack）")
    return parser.parse_args()


if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    try:
        # 调用主函数，传入解析后的参数
        main(liveid=args.liveid, command=args.command, single=args.single, merge=args.no_merge, video_type=args.video_type)
    except Exception as e:
        # 捕获并显示所有未处理的异常
        print(f"发生错误：{e}")
        print(traceback.format_exc())