#!/usr/bin/env python3

import os

def day_to_chinese(day):
    days = ["日", "一", "二", "三", "四", "五", "六"]
    return days[day]

def user_input_with_check(prompt, check_func):
    while True:
        user_input = input(prompt)
        if check_func(user_input):
            return user_input
        else:
            print("输入错误，请重新输入：")

def create_directory(directory):
    os.makedirs(directory, exist_ok=True)
