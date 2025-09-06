#!/usr/bin/env python3
"""
西安电子科技大学录直播平台课程视频下载器 - 主程序
用于下载单门课程的所有视频或指定视频

主要功能：
- 支持交互式和命令行模式下载
- 智能的视频筛选和过滤
- 断点续传和错误恢复
- 自动合并相邻节次视频
- 完整的日志记录和进度跟踪

安全特性：
- 输入验证和参数检查
- 文件完整性验证
- 异常处理和资源清理
- 用户友好的错误提示
"""

import csv
import time
import traceback
import sys
import logging
import concurrent.futures
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone
from tqdm import tqdm
from argparse import ArgumentParser
from api import get_initial_data, get_video_info_from_html, check_update
from downloader import download_mp4, process_rows
from utils import (
    setup_logging, user_input_with_check, remove_invalid_chars,
    create_directory, handle_exception
)
from utils import (day_to_chinese, user_input_with_check, create_directory, 
                   handle_exception, remove_invalid_chars, calculate_optimal_threads)
import concurrent.futures
from threading import Lock

# 使用统一的日志配置
logger = setup_logging('main_downloader', level=logging.INFO, console_level=logging.WARNING)

try:
    # 检查程序更新
    try:
        check_update()
    except Exception as e:
        logger.debug(f"检查更新时出现异常: {e}")
except Exception as e:
    logger.warning(f"版本检查失败，程序继续运行: {e}")


def validate_download_parameters(liveid, single, video_type):
    """
    验证下载参数的有效性。

    参数:
        liveid: 课程直播ID
        single (int): 下载模式
        video_type (str): 视频类型

    返回:
        tuple: (validated_liveid, validated_single, validated_video_type)

    异常:
        ValueError: 当参数无效时
    """
    # 验证liveid
    if liveid is not None:
        try:
            validated_liveid = int(liveid)
            if validated_liveid <= 0:
                raise ValueError("课程ID必须是正整数")
        except (TypeError, ValueError):
            raise ValueError(f"课程ID格式无效: {liveid}")
    else:
        validated_liveid = None

    # 验证single模式
    if not isinstance(single, int) or single < 0 or single > 2:
        raise ValueError("下载模式必须是0（全部）、1（单节课）或2（半节课）")

    # 验证video_type
    if video_type not in ['both', 'ppt', 'teacher']:
        raise ValueError("视频类型必须是 'both', 'ppt' 或 'teacher'")

    return validated_liveid, single, video_type


def get_user_input_interactive():
    """
    交互式模式：获取用户输入参数。

    返回:
        tuple: (liveid, single, merge, video_type, skip_until)
    """
    print("\n" + "="*60)
    print("欢迎使用西安电子科技大学课程视频下载器")
    print("="*60)

    try:
        # 获取课程ID
        liveid = user_input_with_check(
            "请输入课程 liveId：",
            lambda x: x.isdigit() and 1 <= len(x) <= 10,
            error_message="课程ID必须是1-10位数字，请重新输入"
        )
        liveid = int(liveid)

        # 选择下载模式
        print("\n下载模式选择：")
        print("  回车/y - 下载单节课（同一天的所有课程）")
        print("  n - 下载这门课程的所有视频")
        print("  s - 仅下载单集（半节课）视频")
        
        mode_input = user_input_with_check(
            "请选择下载模式 (Y/n/s)：",
            lambda x: x.lower() in ['', 'y', 'n', 's'],
            error_message="请输入 Y、n 或 s"
        ).lower()
        
        single = 1 if mode_input in ['', 'y'] else 2 if mode_input == 's' else 0

        # 选择是否合并视频
        print("\n视频合并选项：")
        print("  回车/y - 自动合并上下半节课视频")
        print("  n - 不合并视频，保持单独文件")
        
        merge_input = user_input_with_check(
            "是否自动合并视频 (Y/n)：",
            lambda x: x.lower() in ['', 'y', 'n'],
            error_message="请输入 Y 或 n"
        ).lower()
        
        merge = merge_input != 'n'

        # 选择视频类型
        print("\n视频类型选择：")
        print("  回车/b - 下载PPT和教师两种视频")
        print("  p - 仅下载PPT演示视频")
        print("  t - 仅下载教师讲课视频")
        
        video_type_input = user_input_with_check(
            "请选择视频类型 (B/p/t)：",
            lambda x: x.lower() in ['', 'b', 'p', 't'],
            error_message="请输入 B、p 或 t"
        ).lower()
        
        video_type = 'ppt' if video_type_input == 'p' else 'teacher' if video_type_input == 't' else 'both'

        # 设置跳过周数
        print("\n高级选项：")
        skip_input = user_input_with_check(
            "从第几周开始下载？（输入周数或回车从第1周开始）：",
            lambda x: x == '' or (x.isdigit() and int(x) >= 1),
            error_message="请输入正整数或直接回车"
        ).strip()
        
        skip_until = int(skip_input) - 1 if skip_input.isdigit() else 0

        return liveid, single, merge, video_type, skip_until

    except KeyboardInterrupt:
        print("\n\n用户取消操作")
        sys.exit(0)
    except Exception as e:
        logger.error(f"获取用户输入时出错: {e}")
        raise


def main(liveid=None, command='', single=0, merge=True, video_type='both'):
    """
    主函数：下载指定课程的视频，包含完整的错误处理和用户体验优化。

    参数:
        liveid (int): 课程直播ID，为None时进入交互模式
        command (str): 自定义下载命令（已弃用）
        single (int): 下载模式 (0=全部, 1=单节课, 2=半节课)
        merge (bool): 是否自动合并相邻节次视频
        video_type (str): 视频类型 ('both', 'ppt', 'teacher')

    返回:
        bool: 处理是否成功
    """
    try:
        logger.info("开始执行视频下载任务")
        
        # 交互模式：用户输入参数
        if liveid is None:
            liveid, single, merge, video_type, skip_until = get_user_input_interactive()
        else:
            # 验证命令行参数
            liveid, single, video_type = validate_download_parameters(liveid, single, video_type)
            skip_until = 0  # 非交互模式下，默认不跳过任何周
            
            if command:
                logger.warning("自定义下载命令参数已弃用")

        logger.info(f"下载参数 - 课程ID: {liveid}, 模式: {single}, 合并: {merge}, 类型: {video_type}")

        # 获取课程的初始数据
        print(f"\n正在获取课程 {liveid} 的信息...")
        try:
            data = get_initial_data(liveid)
        except Exception as e:
            error_msg = handle_exception(e, "获取课程信息失败")
            print(f"\n{error_msg}")
            print("请检查：")
            print("1. 课程ID是否正确")
            print("2. 网络连接是否正常")
            print("3. 是否已正确配置认证信息")
            return False

        # 检查是否获取到有效数据
        if not data:
            print(f"\n没有找到课程 {liveid} 的数据，请检查课程ID是否正确")
            return False

        print(f"成功获取到 {len(data)} 条课程记录")

        # 处理不同的下载模式
        if single:
            original_data = data[:]
            # 筛选出指定liveId的条目
            data = [entry for entry in original_data if entry["id"] == liveid]
            
            if not data:
                logger.error(f"没有找到课程ID {liveid} 对应的课程记录")
                print(f"错误：没有找到课程ID {liveid} 对应的课程记录")
                return False

            if single == 1:
                # 单节课模式：下载同一天的所有课程
                start_time = data[0]["startTime"]
                data = [
                    entry for entry in original_data 
                    if (entry["startTime"]["date"] == start_time["date"] and 
                        entry["startTime"]["month"] == start_time["month"])
                ]
                print(f"单节课模式：将下载 {len(data)} 个视频片段")

        # 提取课程基本信息
        first_entry = data[0]
        year = time.gmtime(first_entry["startTime"]["time"] / 1000).tm_year
        course_code = first_entry.get("courseCode", "未知课程")
        course_name = remove_invalid_chars(first_entry.get("courseName", "未知课程名"))
        
        save_dir = f"{year}年{course_code}{course_name}"
        
        print(f"\n课程信息：")
        print(f"  年份：{year}")
        print(f"  课程代码：{course_code}")
        print(f"  课程名称：{course_name}")
        print(f"  保存目录：{save_dir}")

        # 创建保存目录
        try:
            create_directory(save_dir)
        except OSError as e:
            error_msg = handle_exception(e, "创建保存目录失败")
            print(f"\n{error_msg}")
            return False

        # 多线程获取所有视频的M3U8链接
        print(f"\n正在获取视频链接...")
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

        print(f"找到 {len(valid_entries)} 个可下载的课程片段")

        with tqdm(total=len(valid_entries), desc="获取视频链接") as desc:
            # 计算最佳线程数
            max_threads = calculate_optimal_threads()
            logger.info(f"使用 {max_threads} 个线程获取视频链接")

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                # 提交所有任务
                futures = [
                    executor.submit(fetch_m3u8_links, entry, lock, desc)
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

        print(f"成功获取到 {len(rows)} 个视频链接")

        # 按时间排序：月、日、星期、节次、周数
        rows.sort(key=lambda x: (x[0], x[1], x[2], int(x[3]), x[4]))

        # 根据skip_until参数过滤掉指定周数之前的视频
        if skip_until > 0:
            original_count = len(rows)
            rows = [row for row in rows if int(row[4]) > skip_until]
            filtered_count = original_count - len(rows)
            if filtered_count > 0:
                print(f"根据设置跳过了前 {skip_until} 周的 {filtered_count} 个视频")

        # 保存视频信息到CSV文件
        csv_filename = f"{save_dir}.csv"
        try:
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['month', 'date', 'day', 'jie', 'days', 'pptVideo', 'teacherTrack'])
                writer.writerows(rows)
            print(f"视频信息已保存到：{csv_filename}")
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
                stats = process_rows(
                    download_rows, course_code, course_name, year, 
                    save_dir, command, merge, video_type
                )
                
                print(f"\n下载任务完成！")
                print(f"处理统计：")
                print(f"  - 总计视频：{stats['total_videos']} 个")
                print(f"  - 新下载：{stats['downloaded']} 个")  
                print(f"  - 跳过：{stats['skipped']} 个")
                print(f"  - 失败：{stats['failed']} 个")
                print(f"  - 合并：{stats['merged']} 个")
                
                if stats['failed'] > 0:
                    print(f"\n注意：有 {stats['failed']} 个视频下载失败")
                    print("可能的原因：网络连接问题、服务器限制或认证过期")
                    return False
                    
                return True
                
            except Exception as e:
                error_msg = handle_exception(e, "批量下载处理失败")
                print(f"\n{error_msg}")
                return False

    except KeyboardInterrupt:
        print("\n\n用户取消下载任务")
        return False
    except Exception as e:
        error_msg = handle_exception(e, "下载任务执行失败")
        print(f"\n{error_msg}")
        return False


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


def fetch_m3u8_links(entry, lock, pbar):
    """
    获取单个课程条目的M3U8链接。

    参数:
        entry (dict): 课程条目数据
        lock (Lock): 线程锁
        pbar (tqdm): 进度条对象

    返回:
        list: 视频信息行数据 [月, 日, 星期, 节次, 周数, PPT视频链接, 教师视频链接]
    """
    try:
        # 获取视频信息
        video_info = get_video_info_from_html(entry["id"])
        
        # 更新进度条
        with lock:
            pbar.update(1)
        
        # 检查是否获取到有效的视频信息
        if not video_info or not any(video_info.values()):
            logger.debug(f"课程 {entry['id']} 没有可用的视频链接")
            return None
        
        # 计算日期信息
        start_time = entry["startTime"]
        month = start_time["month"] + 1  # API返回的月份比实际月份小1，需要+1修正
        date = start_time["date"]
        jie = str(entry["jie"])
        
        # 计算星期几和周数
        timestamp = start_time["time"] / 1000
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        day = dt.weekday() + 1  # 转换为星期1-7格式
        
        # 计算学期内的周数
        year = dt.year
        
        # 查找学期开始时间（通常是9月第一周或2月第一周）  
        if month >= 9:
            # 秋季学期
            term_start = datetime(year, 9, 1, tzinfo=timezone.utc)
        else:
            # 春季学期  
            term_start = datetime(year, 2, 1, tzinfo=timezone.utc)
        
        # 计算周数
        days_diff = (dt - term_start).days
        week_number = max(1, (days_diff // 7) + 1)
        
        # 正确提取视频链接 - 处理嵌套的videoPath结构
        video_path = video_info.get("videoPath", {})
        ppt_video = video_path.get("pptVideo", "")
        teacher_track = video_path.get("teacherTrack", "")
        
        return [month, date, day, jie, week_number, ppt_video, teacher_track]
                
    except Exception as e:
        logger.error(f"获取课程 {entry.get('id', 'unknown')} 的视频链接失败: {e}")
        with lock:
            pbar.update(1)
        return None


def calculate_optimal_threads():
    """
    根据系统配置计算最佳线程数。

    返回:
        int: 建议的线程数
    """
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=True)
        memory_gb = psutil.virtual_memory().total / (1024**3)
        
        # 基于CPU和内存计算线程数
        base_threads = min(cpu_count * 2, 16)  # 不超过16个线程
        
        # 根据内存调整
        if memory_gb < 4:
            base_threads = min(base_threads, 4)
        elif memory_gb < 8:
            base_threads = min(base_threads, 8)
        
        return max(2, base_threads)  # 至少2个线程
        
    except ImportError:
        # 如果没有psutil，使用默认值
        import os
        return min(os.cpu_count() or 2, 8)


def day_to_chinese(day_num):
    """
    将数字星期转换为中文。

    参数:
        day_num (int): 星期数字 (1-7)

    返回:
        str: 中文星期
    """
    day_mapping = {
        1: "一", 2: "二", 3: "三", 4: "四", 
        5: "五", 6: "六", 7: "日"
    }
    return day_mapping.get(day_num, str(day_num))


def parse_arguments():
    """
    解析命令行参数。

    返回:
        argparse.Namespace: 包含所有命令行参数的对象
    """
    parser = ArgumentParser(description="用于下载西安电子科技大学录直播平台课程视频的工具")
    parser.add_argument('liveid', nargs='?', default=None, type=int,
                        help="课程的 liveId，不输入则采用交互式方式获取")
    parser.add_argument('-c', '--command', default='',
                        help="自定义下载命令，使用 {url}, {save_dir}, {filename} 作为替换标记（已弃用）")
    parser.add_argument('-s', '--single', action='count',
                        default=0, help="仅下载单节课视频（-s：单节课视频，-ss：半节课视频）")
    parser.add_argument('--no-merge', action='store_false', dest='merge',
                        help="不合并上下半节课视频")
    parser.add_argument('--video-type', choices=['both', 'ppt', 'teacher'], 
                        default='both',
                        help="选择要下载的视频类型：both（两种都下载，默认）、ppt（仅下载pptVideo）、teacher（仅下载teacherTrack）")
    return parser.parse_args()


if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    
    try:
        # 调用主函数，传入解析后的参数
        success = main(
            liveid=args.liveid, 
            command=args.command, 
            single=args.single,
            merge=args.merge, 
            video_type=args.video_type
        )
        
        # 根据执行结果设置退出码
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        sys.exit(130)  # SIGINT 退出码
    except Exception as e:
        # 捕获并显示所有未处理的异常
        logger.error(f"程序执行时发生未处理的异常: {e}")
        print(f"发生错误：{e}")
        if logger.getEffectiveLevel() <= logging.DEBUG:
            print(traceback.format_exc())
        sys.exit(1)
