#!/usr/bin/env python3
"""
工具模块
提供各种辅助函数，包括文件处理、配置管理、系统资源监控等功能
"""

import os
import configparser
import traceback
import psutil
from datetime import datetime

def remove_invalid_chars(course_name):
    """
    移除文件名中的非法字符，确保可以在文件系统中创建文件。
    
    参数:
        course_name (str): 原始课程名称
        
    返回:
        str: 移除非法字符后的课程名称
    """
    # 定义 Windows/Linux 文件系统中不允许的字符
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    # 逐个替换非法字符为空字符串
    for char in invalid_chars:
        course_name = course_name.replace(char, '')
    return course_name

def day_to_chinese(day):
    """
    将星期数字转换为中文表示。
    
    参数:
        day (int): 星期数字 (0-6, 0代表星期日)
        
    返回:
        str: 对应的中文星期表示
    """
    # 星期数字到中文的映射字典
    days = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
    return days.get(day, "未知")

def user_input_with_check(prompt, check_func):
    """
    带验证功能的用户输入函数，会循环提示直到输入合法。
    
    参数:
        prompt (str): 提示信息
        check_func (function): 验证函数，返回True表示输入合法
        
    返回:
        str: 验证通过的用户输入
    """
    # 使用海象运算符在while条件中同时赋值和检查
    while not check_func(user_input := input(prompt)):
        print("输入错误，请重新输入：")
    return user_input

def create_directory(directory):
    """
    创建目录，如果目录已存在则不会报错。
    
    参数:
        directory (str): 要创建的目录路径
    """
    # exist_ok=True 确保目录已存在时不会抛出异常
    os.makedirs(directory, exist_ok=True)

def write_config(config, user_id, courses, video_type='both'):
    """
    将用户信息和课程信息写入配置文件。
    
    参数:
        config (ConfigParser): 配置解析器对象
        user_id (str): 用户ID
        courses (dict): 课程信息字典
        video_type (str): 视频类型，默认为'both'
    """
    # Extract term information from the context - since all courses come from scan_courses
    # with specific term_year and term_id, we can determine these from the current context
    current_date = datetime.now()
    current_year = current_date.year
    month = current_date.month
    
    # Determine current term based on date logic (same as Automation.py)
    # 根据当前月份确定学期信息
    term_year = current_year
    term_id = 1 if month >= 9 else 2  # 9月及以后为第一学期，否则为第二学期
    if month < 8:  # 如果是1-7月，说明还是上一学年的第二学期
        term_year -= 1
    
    # 写入默认配置段
    config['DEFAULT'] = {
        'user_id': user_id,
        'term_year': term_year,
        'term_id': term_id,
        'video_type': video_type
    }
    # 写入每门课程的配置信息
    for course_id, course in courses.items():
        config[course_id] = {
            'course_code': course['courseCode'],
            'course_name': remove_invalid_chars(course['courseName']),  # 移除文件名非法字符
            'live_id': course['id'],
            'download': 'yes'  # 默认设置为下载
        }
    # 将配置写入文件
    with open('config.ini', 'w', encoding='utf-8') as configfile:
        config.write(configfile)

def read_config():
    """
    从config.ini文件读取配置信息。
    
    返回:
        ConfigParser: 包含配置信息的配置解析器对象
    """
    config = configparser.ConfigParser()
    # 使用UTF-8编码读取配置文件
    config.read('config.ini', encoding='utf-8')
    return config

def handle_exception(e, message):
    """
    统一的异常处理函数，打印错误信息和详细的堆栈跟踪。
    
    参数:
        e (Exception): 异常对象
        message (str): 自定义错误消息
    """
    # 打印自定义错误消息和详细的堆栈跟踪信息
    print(f"{message}：\n{traceback.format_exc()}")

def calculate_optimal_threads():
    """
    根据 CPU 负载和内存使用情况计算最佳线程数。
    
    返回:
        int: 推荐的线程数量
    """
    # 获取当前系统的CPU和内存使用率
    cpu_usage = psutil.cpu_percent()
    mem_usage = psutil.virtual_memory().percent

    # 获取CPU核心数
    cpu_count = os.cpu_count()

    # 根据 CPU 使用率和内存使用率进行调整
    if cpu_usage > 80 or mem_usage > 80:
        # 系统负载高时，使用较少线程避免过载
        max_threads = cpu_count
    elif cpu_usage < 30 and mem_usage < 30:
        # 系统负载低时，可以使用更多线程提高效率
        max_threads = cpu_count * 4
    else:
        # 中等负载时，使用适中的线程数
        max_threads = cpu_count * 2

    # 确保线程数在合理范围内：最小是核心数，最大是核心数的8倍
    max_threads = min(max(max_threads, cpu_count), cpu_count * 8)
    return int(max_threads)
