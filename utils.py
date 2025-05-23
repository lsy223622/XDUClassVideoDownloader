#!/usr/bin/env python3

import os
import configparser
import traceback

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
