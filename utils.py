#!/usr/bin/env python3
"""
工具模块
提供各种辅助函数，包括文件处理、配置管理、系统资源监控等功能

主要功能：
- 文件系统操作和路径处理
- 配置文件管理
- 用户输入验证和交互
- 系统资源监控
- 安全的认证信息管理
- 统一的异常处理和日志记录
"""

import os
import sys
import re
import configparser
import traceback
import psutil
import stat
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
import logging


# 配置基础日志记录 - 只保存到文件
from pathlib import Path

logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'xdu_downloader.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def setup_logging(name='xdu_downloader', level=logging.INFO, console_level=logging.WARNING):
    """
    设置日志记录系统。
    
    详细日志保存到文件中，用户界面只显示警告和错误信息。

    参数:
        name (str): 日志记录器名称
        level: 文件日志级别
        console_level: 控制台日志级别（默认只显示WARNING及以上）

    返回:
        logging.Logger: 配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 创建日志目录
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # 创建文件处理器 - 记录所有日志信息
    file_handler = logging.FileHandler(log_dir / f'{name}.log', encoding='utf-8')
    file_handler.setLevel(level)
    
    # 创建控制台处理器 - 只显示重要信息
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    
    # 创建详细的文件格式化器
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建简洁的控制台格式化器
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # 设置格式化器
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def remove_invalid_chars(course_name):
    """
    移除文件名中的非法字符，确保可以在文件系统中创建文件。
    
    使用更安全和全面的字符过滤方法，同时保持文件名的可读性。

    参数:
        course_name (str): 原始课程名称

    返回:
        str: 移除非法字符后的课程名称

    异常:
        ValueError: 当输入为空或处理后名称为空时
    """
    if not course_name or not isinstance(course_name, str):
        raise ValueError("课程名称不能为空且必须是字符串类型")
    
    # 定义 Windows/Linux 文件系统中不允许的字符
    # 包括控制字符和保留字符
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\0']
    
    # 移除控制字符 (ASCII 0-31)
    cleaned_name = ''.join(char for char in course_name if ord(char) >= 32)
    
    # 替换非法字符为下划线，保持可读性
    for char in invalid_chars:
        cleaned_name = cleaned_name.replace(char, '_')
    
    # 移除首尾空白字符和点号（Windows不允许）
    cleaned_name = cleaned_name.strip(' .')
    
    # 检查 Windows 保留文件名
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + \
                    [f'COM{i}' for i in range(1, 10)] + \
                    [f'LPT{i}' for i in range(1, 10)]
    
    if cleaned_name.upper() in reserved_names:
        cleaned_name = f"_{cleaned_name}"
    
    # 限制文件名长度，避免路径过长问题
    if len(cleaned_name) > 100:
        cleaned_name = cleaned_name[:100].rstrip()
    
    if not cleaned_name:
        raise ValueError("处理后的课程名称为空，请检查原始名称")
    
    return cleaned_name


def day_to_chinese(day):
    """
    将星期数字转换为中文表示。

    参数:
        day (int): 星期数字 (0-6, 0代表星期日)

    返回:
        str: 对应的中文星期表示

    异常:
        ValueError: 当输入不是有效的星期数字时
    """
    if not isinstance(day, int):
        try:
            day = int(day)
        except (TypeError, ValueError):
            raise ValueError(f"星期数字必须是整数，收到：{type(day).__name__}")
    
    # 星期数字到中文的映射字典
    days = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
    
    if day not in days:
        raise ValueError(f"星期数字必须在0-6范围内，收到：{day}")
    
    return days[day]


def validate_input(value, validator, error_message="输入格式错误"):
    """
    验证用户输入的通用函数。

    参数:
        value: 待验证的值
        validator: 验证函数或正则表达式
        error_message (str): 验证失败时的错误消息

    返回:
        bool: 验证是否通过

    异常:
        ValueError: 当验证器类型不正确时
    """
    try:
        if callable(validator):
            return validator(value)
        elif isinstance(validator, str):
            # 作为正则表达式处理
            return bool(re.match(validator, str(value)))
        else:
            raise ValueError("验证器必须是函数或正则表达式字符串")
    except Exception as e:
        logger.warning(f"输入验证失败: {e}")
        return False


def user_input_with_check(prompt, validator, max_attempts=3, error_message="输入格式错误，请重新输入"):
    """
    带验证功能的用户输入函数，提供更好的用户体验和安全性。

    参数:
        prompt (str): 提示信息
        validator: 验证函数或正则表达式
        max_attempts (int): 最大尝试次数
        error_message (str): 验证失败时的错误消息

    返回:
        str: 验证通过的用户输入

    异常:
        ValueError: 超过最大尝试次数时
    """
    attempts = 0
    while attempts < max_attempts:
        try:
            user_input = input(prompt).strip()
            if validate_input(user_input, validator):
                return user_input
            else:
                print(error_message)
                attempts += 1
        except KeyboardInterrupt:
            print("\n用户中断操作")
            raise
        except EOFError:
            print("\n输入流结束")
            raise ValueError("输入流意外结束")
    
    raise ValueError(f"超过最大尝试次数 ({max_attempts})，输入验证失败")


def create_directory(directory):
    """
    安全地创建目录，包含权限设置和原子性保证。

    参数:
        directory (str): 要创建的目录路径

    异常:
        OSError: 创建目录失败时
        ValueError: 路径参数无效时
    """
    if not directory or not isinstance(directory, str):
        raise ValueError("目录路径不能为空且必须是字符串类型")
    
    try:
        # 使用 Path 对象处理路径，更安全
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        
        # 设置适当的权限 (仅在Unix系统上有效)
        if os.name == 'posix':
            try:
                os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
            except OSError:
                logger.warning(f"无法设置目录权限: {directory}")
        
        logger.info(f"目录创建成功: {directory}")
        
    except OSError as e:
        logger.error(f"创建目录失败: {directory}, 错误: {e}")
        raise OSError(f"无法创建目录 {directory}: {e}")


def safe_write_config(config, filename, backup=True):
    """
    安全地写入配置文件，包含备份和原子性保证。

    参数:
        config (ConfigParser): 配置对象
        filename (str): 配置文件名
        backup (bool): 是否创建备份

    异常:
        OSError: 文件写入失败时
    """
    filepath = Path(filename)
    
    # 创建备份
    if backup and filepath.exists():
        backup_path = filepath.with_suffix(f'.bak.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        try:
            shutil.copy2(filepath, backup_path)
            logger.info(f"配置文件备份已创建: {backup_path}")
        except OSError as e:
            logger.warning(f"无法创建配置文件备份: {e}")
    
    # 原子性写入：先写入临时文件，再重命名
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', 
            encoding='utf-8', 
            delete=False,
            dir=filepath.parent,
            prefix=f'.{filepath.name}.tmp'
        ) as temp_file:
            config.write(temp_file)
            temp_path = temp_file.name
        
        # 原子性重命名
        shutil.move(temp_path, filepath)
        logger.info(f"配置文件写入成功: {filename}")
        
    except Exception as e:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except OSError:
                pass
        raise OSError(f"写入配置文件失败 {filename}: {e}")


def write_config(config, user_id, courses, video_type='both'):
    """
    将用户信息和课程信息写入配置文件。

    参数:
        config (ConfigParser): 配置解析器对象
        user_id (str): 用户ID
        courses (dict): 课程信息字典
        video_type (str): 视频类型，默认为'both'

    异常:
        ValueError: 参数验证失败时
        OSError: 文件操作失败时
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("用户ID不能为空且必须是字符串类型")
    
    if not courses or not isinstance(courses, dict):
        raise ValueError("课程信息不能为空且必须是字典类型")
    
    if video_type not in ['both', 'ppt', 'teacher']:
        raise ValueError("视频类型必须是 'both', 'ppt' 或 'teacher'")
    
    try:
        # 确定学期信息
        current_date = datetime.now()
        current_year = current_date.year
        month = current_date.month

        # 根据当前月份确定学期信息
        term_year = current_year
        term_id = 1 if month >= 9 else 2  # 9月及以后为第一学期，否则为第二学期
        if month < 8:  # 如果是1-7月，说明还是上一学年的第二学期
            term_year -= 1

        # 清除现有配置并写入默认配置段
        config.clear()
        config['DEFAULT'] = {
            'user_id': user_id,
            'term_year': str(term_year),
            'term_id': str(term_id),
            'video_type': video_type
        }
        
        # 写入每门课程的配置信息
        for course_id, course in courses.items():
            if not isinstance(course, dict):
                logger.warning(f"跳过无效的课程数据: {course_id}")
                continue
            
            config[str(course_id)] = {
                'course_code': course.get('courseCode', ''),
                'course_name': remove_invalid_chars(course.get('courseName', '')),
                'live_id': str(course.get('id', '')),
                'download': 'yes'  # 默认设置为下载
            }
        
        # 安全写入配置文件
        safe_write_config(config, 'config.ini')
        logger.info(f"配置文件已创建，包含 {len(courses)} 门课程")
        
    except Exception as e:
        logger.error(f"写入配置文件失败: {e}")
        raise


def read_config():
    """
    从config.ini文件读取配置信息，包含错误处理和验证。

    返回:
        ConfigParser: 包含配置信息的配置解析器对象

    异常:
        FileNotFoundError: 配置文件不存在时
        configparser.Error: 配置文件格式错误时
    """
    config_file = 'config.ini'
    
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    config = configparser.ConfigParser()
    try:
        # 使用UTF-8编码读取配置文件
        config.read(config_file, encoding='utf-8')
        
        # 验证基本的配置结构
        if 'DEFAULT' not in config:
            raise configparser.Error("配置文件缺少 DEFAULT 段")
        
        required_keys = ['user_id', 'term_year', 'term_id']
        for key in required_keys:
            if key not in config['DEFAULT']:
                raise configparser.Error(f"配置文件缺少必要的配置项: {key}")
        
        logger.info(f"配置文件读取成功: {config_file}")
        return config
        
    except configparser.Error as e:
        logger.error(f"配置文件格式错误: {e}")
        raise
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
        raise


def get_auth_cookies(fid=None):
    """
    获取身份验证所需的cookie信息，包含安全性改进。
    如果配置文件中不存在，则提示用户输入并安全保存。

    参数:
        fid (str): 可选的FID值

    返回:
        dict: 包含身份验证cookie的字典

    异常:
        ValueError: 当认证信息无效时
    """
    config = configparser.ConfigParser(interpolation=None)
    # 保持键的大小写
    config.optionxform = str
    auth_config_file = 'auth.ini'

    # 尝试读取现有的认证配置
    if os.path.exists(auth_config_file):
        try:
            config.read(auth_config_file, encoding='utf-8')
            if 'AUTH' in config and all(key in config['AUTH'] for key in ['_d', 'UID', 'vc3']):
                auth_data = dict(config['AUTH'])
                auth_data['fid'] = fid or ''
                logger.info("从配置文件读取认证信息成功")
                return auth_data
        except Exception as e:
            logger.warning(f"读取认证配置失败: {e}")

    # 如果配置不存在或不完整，则提示用户输入
    print("\n" + "="*60)
    print("需要进行身份验证以访问课程视频")
    print("请按照以下步骤获取认证信息：")
    print("1. 在浏览器中访问 https://chaoxing.com/ 并登录")
    print("2. 访问 https://i.mooc.chaoxing.com/")
    print("3. 按F12打开开发者工具，在Application->Cookies中找到以下值")
    print("="*60)

    # 验证函数
    def validate_cookie_value(value):
        return bool(value and len(value.strip()) > 0 and not any(char in value for char in ['\n', '\r', '\t']))

    try:
        auth_cookies = {}
        auth_cookies['fid'] = fid or ''
        
        # 获取认证信息，增加输入验证
        auth_cookies['_d'] = user_input_with_check(
            "请输入 _d 的值: ",
            validate_cookie_value,
            error_message="Cookie值不能为空且不能包含换行符，请重新输入"
        ).strip()
        
        auth_cookies['UID'] = user_input_with_check(
            "请输入 UID 的值: ",
            validate_cookie_value,
            error_message="Cookie值不能为空且不能包含换行符，请重新输入"
        ).strip()
        
        auth_cookies['vc3'] = user_input_with_check(
            "请输入 vc3 的值: ",
            validate_cookie_value,
            error_message="Cookie值不能为空且不能包含换行符，请重新输入"
        ).strip()

        # 安全保存到配置文件
        config['AUTH'] = {k: v for k, v in auth_cookies.items() if k != 'fid'}
        safe_write_config(config, auth_config_file)
        
        # 设置配置文件权限（仅Unix系统）
        if os.name == 'posix':
            try:
                os.chmod(auth_config_file, stat.S_IRUSR | stat.S_IWUSR)
                logger.info("认证文件权限设置成功")
            except OSError as e:
                logger.warning(f"无法设置认证文件权限: {e}")

        print("认证信息已安全保存")
        logger.info("新的认证信息已保存")
        return auth_cookies
        
    except (KeyboardInterrupt, EOFError):
        print("\n用户取消认证设置")
        raise ValueError("用户取消认证设置")
    except Exception as e:
        logger.error(f"获取认证信息失败: {e}")
        raise ValueError(f"获取认证信息失败: {e}")


def format_auth_cookies(auth_cookies):
    """
    将认证cookie字典格式化为HTTP请求可用的cookie字符串。

    参数:
        auth_cookies (dict): 包含认证信息的字典

    返回:
        str: 格式化的cookie字符串

    异常:
        ValueError: 当认证信息格式错误时
    """
    if not isinstance(auth_cookies, dict):
        raise ValueError("认证信息必须是字典类型")
    
    required_keys = ['_d', 'UID', 'vc3']
    for key in required_keys:
        if key not in auth_cookies:
            raise ValueError(f"缺少必要的认证信息: {key}")
        if not auth_cookies[key]:
            raise ValueError(f"认证信息不能为空: {key}")
    
    fid_value = auth_cookies.get('fid', '')
    cookie_string = f"fid={fid_value}; _d={auth_cookies['_d']}; UID={auth_cookies['UID']}; vc3={auth_cookies['vc3']}"
    
    return cookie_string


def handle_exception(e, message, level=logging.ERROR):
    """
    统一的异常处理函数，提供更安全的错误信息记录。

    参数:
        e (Exception): 异常对象
        message (str): 自定义错误消息
        level: 日志级别

    返回:
        str: 用户友好的错误消息
    """
    # 生成用户友好的错误消息
    if isinstance(e, (ConnectionError, OSError)):
        user_message = f"{message}：网络连接或文件操作失败"
    elif isinstance(e, ValueError):
        user_message = f"{message}：输入数据格式错误"
    elif isinstance(e, KeyError):
        user_message = f"{message}：缺少必要的数据字段"
    elif isinstance(e, FileNotFoundError):
        user_message = f"{message}：找不到所需文件"
    else:
        user_message = f"{message}：操作失败"
    
    # 记录详细的技术错误信息到日志
    logger.log(level, f"{message}: {type(e).__name__}: {str(e)}", exc_info=True)
    
    # 向用户显示友好的错误消息
    print(user_message)
    return user_message


def calculate_optimal_threads():
    """
    根据 CPU 负载和内存使用情况计算最佳线程数，增加了安全边界。

    返回:
        int: 推荐的线程数量
    """
    try:
        # 获取当前系统的CPU和内存使用率
        cpu_usage = psutil.cpu_percent(interval=1)  # 增加采样时间提高准确性
        mem_usage = psutil.virtual_memory().percent
        cpu_count = os.cpu_count() or 4  # 提供默认值

        logger.info(f"系统状态 - CPU使用率: {cpu_usage}%, 内存使用率: {mem_usage}%, CPU核心数: {cpu_count}")

        # 根据系统负载动态调整线程数
        if cpu_usage > 80 or mem_usage > 85:
            # 系统负载高时，使用保守的线程数
            max_threads = max(1, cpu_count // 2)
        elif cpu_usage < 20 and mem_usage < 50:
            # 系统负载低时，可以使用更多线程
            max_threads = cpu_count * 3
        else:
            # 中等负载时，使用适中的线程数
            max_threads = cpu_count * 2

        # 安全边界：确保线程数在合理范围内
        max_threads = max(1, min(max_threads, cpu_count * 4, 32))  # 最大不超过32个线程
        
        logger.info(f"计算得出最佳线程数: {max_threads}")
        return int(max_threads)
        
    except Exception as e:
        logger.warning(f"计算最佳线程数失败，使用默认值: {e}")
        return 4  # 保守的默认值


def format_file_size(size_bytes):
    """
    将字节数格式化为人类可读的文件大小。

    参数:
        size_bytes (int): 文件大小（字节）

    返回:
        str: 格式化的文件大小字符串
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def is_valid_url(url):
    """
    验证URL格式是否有效。

    参数:
        url (str): 待验证的URL

    返回:
        bool: URL是否有效
    """
    if not url or not isinstance(url, str):
        return False
    
    # 基本的URL格式验证
    url_pattern = re.compile(
        r'^https?://'  # http:// 或 https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP地址
        r'(?::\d+)?'  # 可选端口
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))


def get_safe_filename(filename, max_length=255):
    """
    获取安全的文件名，处理长度限制和特殊字符。

    参数:
        filename (str): 原始文件名
        max_length (int): 最大文件名长度

    返回:
        str: 安全的文件名
    """
    if not filename:
        return "unnamed_file"
    
    # 移除非法字符
    safe_name = remove_invalid_chars(filename)
    
    # 处理长度限制
    if len(safe_name) > max_length:
        # 保留文件扩展名
        name_part, ext_part = os.path.splitext(safe_name)
        available_length = max_length - len(ext_part)
        if available_length > 0:
            safe_name = name_part[:available_length] + ext_part
        else:
            safe_name = safe_name[:max_length]
    
    return safe_name or "unnamed_file"


def safe_read_config(filename):
    """
    安全地读取配置文件。

    参数:
        filename (str): 配置文件路径

    返回:
        configparser.ConfigParser: 配置对象

    异常:
        FileNotFoundError: 配置文件不存在
        configparser.Error: 配置文件格式错误
    """
    import configparser
    
    if not Path(filename).exists():
        raise FileNotFoundError(f"配置文件不存在: {filename}")
    
    config = configparser.ConfigParser()
    
    try:
        config.read(filename, encoding='utf-8')
        logger.debug(f"成功读取配置文件: {filename}")
        return config
    except configparser.Error as e:
        logger.error(f"配置文件格式错误: {e}")
        raise
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
        raise


def validate_user_id(user_id):
    """
    验证用户ID的有效性。

    参数:
        user_id (str): 用户ID

    返回:
        bool: 是否有效
    """
    if not user_id or not isinstance(user_id, str):
        return False
    
    # 用户ID应该是数字字符串，长度在6-20之间
    user_id = user_id.strip()
    if not user_id.isdigit():
        return False
    
    if len(user_id) < 6 or len(user_id) > 20:
        return False
    
    return True


def validate_term_params(year, term_id):
    """
    验证学期参数的有效性。

    参数:
        year (int): 学年
        term_id (int): 学期ID

    返回:
        bool: 是否有效
    """
    try:
        year = int(year)
        term_id = int(term_id)
        
        # 学年应该在合理范围内
        current_year = datetime.now().year
        if year < 2000 or year > current_year + 1:
            return False
        
        # 学期ID应该是1或2
        if term_id not in [1, 2]:
            return False
        
        return True
    except (ValueError, TypeError):
        return False
