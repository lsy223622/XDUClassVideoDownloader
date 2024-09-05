#!/usr/bin/env python3

import os
import configparser

def day_to_chinese(day):
    days = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
    return days.get(day, "未知")

def user_input_with_check(prompt, check_func):
    while True:
        user_input = input(prompt)
        if check_func(user_input):
            return user_input
        else:
            print("输入错误，请重新输入：")

def create_directory(directory):
    os.makedirs(directory, exist_ok=True)

def write_config(config, user_id, courses):
    config['DEFAULT'] = {'user_id': user_id}
    for course_id, course in courses.items():
        config[course_id] = {
            'course_code': course['courseCode'],
            'course_name': course['courseName'],
            'live_id': course['id'],
            'download': 'yes'
        }
    with open('config.ini', 'w') as configfile:
        config.write(configfile)

def read_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config
