#!/usr/bin/env python3

import os
import configparser
import traceback
import psutil

def remove_invalid_chars(course_name):
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        course_name = course_name.replace(char, '')
    return course_name

def day_to_chinese(day):
    days = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
    return days.get(day, "未知")

def user_input_with_check(prompt, check_func):
    while not check_func(user_input := input(prompt)):
        print("输入错误，请重新输入：")
    return user_input

def create_directory(directory):
    os.makedirs(directory, exist_ok=True)

def write_config(config, user_id, courses):
    config['DEFAULT'] = {
        'user_id': user_id,
        'term_year': '',
        'term_id': ''
    }
    for course_id, course in courses.items():
        config[course_id] = {
            'course_code': course['courseCode'],
            'course_name': remove_invalid_chars(course['courseName']),
            'live_id': course['id'],
            'download': 'yes'
        }
    with open('config.ini', 'w', encoding='utf-8') as configfile:
        config.write(configfile)

def read_config():
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    return config

def handle_exception(e, message):
    print(f"{message}：\n{traceback.format_exc()}")

def calculate_optimal_threads():
    """
    根据 CPU 负载和内存使用情况计算最佳线程数。
    """
    cpu_usage = psutil.cpu_percent()
    mem_usage = psutil.virtual_memory().percent

    cpu_count = os.cpu_count()

    # 根据 CPU 使用率和内存使用率进行调整
    if cpu_usage > 80 or mem_usage > 80:
        max_threads = cpu_count
    elif cpu_usage < 30 and mem_usage < 30:
        max_threads = cpu_count * 4
    else:
        max_threads = cpu_count * 2

    max_threads = min(max(max_threads, cpu_count), cpu_count * 8) # 最小是核心数，最大是核心数的8倍
    return int(max_threads)
