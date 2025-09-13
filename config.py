#!/usr/bin/env python3
"""
配置管理模块
专门负责所有配置文件的读写和管理操作

主要功能：
- 配置文件的安全读写
- 认证信息管理
- 课程配置管理
- 配置文件备份和恢复
"""

import os
import configparser
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from utils import remove_invalid_chars, setup_logging, handle_exception
from validator import validate_user_id, validate_term_params

# 配置日志（模块日志 + 总日志；控制台仅 error+）
logger = setup_logging('config')

# 配置文件名
AUTOMATION_CONFIG_FILE = 'automation_config.ini'
AUTH_CONFIG_FILE = 'auth.ini'

# 运行期（进程内）认证信息缓存：确保一次运行内仅登录一次
# 形如 {'_d': '...', 'UID': '...', 'vc3': '...', 'fid': '...'}
_runtime_auth_cache = None


def safe_write_config(config, filename, backup=False):
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

    # 创建备份到 logs 目录
    if backup and filepath.exists():
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)

        backup_filename = f"{filepath.stem}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}{filepath.suffix}"
        backup_path = logs_dir / backup_filename
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


def get_auth_cookies(fid=None, *, force_refresh=False):
    """
    获取身份验证所需的cookie信息。
    支持两种认证方式：账号密码登录和直接使用cookies。

    参数:
        fid (str): 可选的FID值

    返回:
        dict: 包含身份验证cookie的字典

    异常:
        ValueError: 当认证信息无效时
    """
    global _runtime_auth_cache

    # 运行期缓存优先（除非强制刷新）
    if not force_refresh and isinstance(_runtime_auth_cache, dict):
        try:
            if all(_runtime_auth_cache.get(k) for k in ['_d', 'UID', 'vc3']):
                # 按需覆盖/补充 fid（不改变其它键）
                if fid is not None:
                    _runtime_auth_cache['fid'] = fid or ''
                logger.debug("使用运行期缓存的认证信息（本次运行内复用）")
                return _runtime_auth_cache
        except Exception:
            # 缓存结构异常则丢弃，走后续正常流程
            _runtime_auth_cache = None

    config = configparser.ConfigParser(interpolation=None)
    # 保持键的大小写
    config.optionxform = str

    # 读取认证配置
    auth_method = 'cookies'  # 默认使用cookies方式
    save_auth_info = True    # 默认保存认证信息
    auth_data = {}

    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            config.read(AUTH_CONFIG_FILE, encoding='utf-8')
            if 'SETTINGS' in config:
                auth_method = config['SETTINGS'].get('auth_method', 'cookies')
                save_auth_info = config['SETTINGS'].getboolean('save_auth_info', True)
                logger.info(f"从配置文件读取认证设置: 方式={auth_method}, 保存={save_auth_info}")
        except Exception as e:
            logger.warning(f"读取认证配置失败: {e}")

    # 如果保存认证信息，尝试从配置文件读取
    if save_auth_info and os.path.exists(AUTH_CONFIG_FILE):
        try:
            if auth_method == 'cookies' and 'AUTH' in config:
                if all(key in config['AUTH'] for key in ['_d', 'UID', 'vc3']):
                    auth_data = dict(config['AUTH'])
                    auth_data['fid'] = fid or ''
                    logger.info("从配置文件读取cookies认证信息成功")
                    # 写入运行期缓存
                    global _runtime_auth_cache
                    _runtime_auth_cache = dict(auth_data)
                    return auth_data
            elif auth_method == 'password' and 'CREDENTIALS' in config:
                if all(key in config['CREDENTIALS'] for key in ['username', 'password']):
                    username = config['CREDENTIALS']['username']
                    password = config['CREDENTIALS']['password']
                    logger.info("从配置文件读取账号密码，开始登录获取cookies")

                    # 导入登录函数
                    from api import get_three_cookies_from_login

                    try:
                        cookies = get_three_cookies_from_login(username, password)
                        if all(cookies.get(key) for key in ['_d', 'UID', 'vc3']):
                            cookies['fid'] = fid or ''
                            logger.info("通过账号密码登录获取cookies成功")
                            # 写入运行期缓存，确保本次运行仅登录一次
                            _runtime_auth_cache = dict(cookies)
                            return _runtime_auth_cache
                        else:
                            logger.error("登录成功但获取的cookies不完整")
                    except Exception as e:
                        logger.error(f"通过账号密码登录失败: {e}")
                        # 登录失败，清除保存的认证信息并要求重新输入
                        print(f"使用保存的账号密码登录失败: {e}")
                        print("将要求重新输入认证信息")
        except Exception as e:
            logger.warning(f"读取保存的认证信息失败: {e}")

    # 需要重新获取认证信息
    # 交互式获取：获取成功后也写入运行期缓存
    cookies = _get_auth_info_interactively(config, fid)
    try:
        if isinstance(cookies, dict) and all(cookies.get(k) for k in ['_d', 'UID', 'vc3']):
            _runtime_auth_cache = dict(cookies)
            logger.debug("已缓存认证信息用于本次运行")
    except Exception:
        pass
    return cookies


def _get_auth_info_interactively(config, fid):
    """
    交互式获取认证信息。

    参数:
        config: 配置对象
        fid: FID值

    返回:
        dict: 认证cookie字典
    """
    print("\n" + "="*60)
    print("需要进行身份验证以访问课程视频")
    print("="*60)

    # 选择认证方式
    print("\n请选择认证方式：")
    print("1. 使用账号密码（推荐，自动获取最新cookies）")
    print("2. 手动输入cookies")

    def validate_auth_method_choice(choice):
        return choice in ['1', '2']

    try:
        from utils import user_input_with_check

        auth_method_choice = user_input_with_check(
            "请输入选择（1或2）: ",
            validate_auth_method_choice,
            error_message="选择无效，请输入1或2"
        ).strip()

        auth_method = 'password' if auth_method_choice == '1' else 'cookies'

        # 选择是否保存认证信息
        print("\n是否保存认证信息以便下次使用？")
        print("1. 是（推荐）")
        print("2. 否（每次都重新输入）")

        def validate_save_choice(choice):
            return choice in ['1', '2']

        save_choice = user_input_with_check(
            "请输入选择（1或2）: ",
            validate_save_choice,
            error_message="选择无效，请输入1或2"
        ).strip()

        save_auth_info = save_choice == '1'

        # 根据选择的方式获取认证信息
        if auth_method == 'password':
            auth_cookies = _get_cookies_from_password(fid)
        else:
            auth_cookies = _get_cookies_manually(fid)

        # 保存设置和认证信息
        if save_auth_info:
            _save_auth_config(config, auth_method, save_auth_info, auth_cookies, auth_method == 'password')
        else:
            # 只保存设置，不保存认证信息
            _save_auth_settings(config, auth_method, save_auth_info)

        return auth_cookies

    except (KeyboardInterrupt, EOFError):
        print("\n用户取消认证设置")
        raise ValueError("用户取消认证设置")
    except Exception as e:
        logger.error(f"获取认证信息失败: {e}")
        raise ValueError(f"获取认证信息失败: {e}")


def _get_cookies_from_password(fid):
    """
    通过账号密码获取cookies。

    参数:
        fid: FID值

    返回:
        dict: 认证cookie字典
    """
    def validate_non_empty(value):
        return bool(value and len(value.strip()) > 0)

    try:
        from utils import user_input_with_check
        from api import get_three_cookies_from_login

        print("\n请输入您的超星账号信息：")
        username = user_input_with_check(
            "用户名: ",
            validate_non_empty,
            error_message="用户名不能为空，请重新输入"
        ).strip()

        password = user_input_with_check(
            "密码: ",
            validate_non_empty,
            error_message="密码不能为空，请重新输入"
        ).strip()

        print("正在登录并获取认证信息...")
        cookies = get_three_cookies_from_login(username, password)

        if not all(cookies.get(key) for key in ['_d', 'UID', 'vc3']):
            raise ValueError("登录成功但获取的cookies不完整")

        cookies['fid'] = fid or ''
        cookies['username'] = username  # 保存用户名用于配置文件
        cookies['password'] = password  # 保存密码用于配置文件

        print("登录成功，认证信息获取完成")
        logger.info("通过账号密码登录获取cookies成功")
        # 写入运行期缓存
        global _runtime_auth_cache
        _runtime_auth_cache = dict(cookies)
        return cookies

    except Exception as e:
        logger.error(f"账号密码登录失败: {e}")
        raise ValueError(f"账号密码登录失败: {e}")


def _get_cookies_manually(fid):
    """
    手动输入cookies。

    参数:
        fid: FID值

    返回:
        dict: 认证cookie字典
    """
    print("\n请按照以下步骤获取认证信息：")
    print("1. 在浏览器中访问 https://chaoxing.com/ 并登录")
    print("2. 访问 https://i.mooc.chaoxing.com/")
    print("3. 按F12打开开发者工具，在Application->Cookies中找到以下值")
    print("-" * 60)

    def validate_cookie_value(value):
        return bool(value and len(value.strip()) > 0 and not any(char in value for char in ['\n', '\r', '\t']))

    try:
        from utils import user_input_with_check

        auth_cookies = {'fid': fid or ''}

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

        print("认证信息输入完成")
        logger.info("手动输入cookies完成")
        # 写入运行期缓存
        global _runtime_auth_cache
        _runtime_auth_cache = dict(auth_cookies)
        return auth_cookies

    except Exception as e:
        logger.error(f"手动输入cookies失败: {e}")
        raise ValueError(f"手动输入cookies失败: {e}")


def _save_auth_config(config, auth_method, save_auth_info, auth_cookies, include_credentials):
    """
    保存认证配置到文件。

    参数:
        config: 配置对象
        auth_method: 认证方式
        save_auth_info: 是否保存认证信息
        auth_cookies: 认证cookie字典
        include_credentials: 是否包含账号密码
    """
    try:
        # 保存设置
        config['SETTINGS'] = {
            'auth_method': auth_method,
            'save_auth_info': str(save_auth_info)
        }

        # 保存认证信息
        if auth_method == 'cookies':
            config['AUTH'] = {k: v for k, v in auth_cookies.items() if k in ['_d', 'UID', 'vc3']}
        elif auth_method == 'password' and include_credentials:
            config['CREDENTIALS'] = {
                'username': auth_cookies.get('username', ''),
                'password': auth_cookies.get('password', '')
            }

        safe_write_config(config, AUTH_CONFIG_FILE)

        # 设置配置文件权限（仅Unix系统）
        if os.name == 'posix':
            try:
                import stat
                os.chmod(AUTH_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
                logger.info("认证文件权限设置成功")
            except OSError as e:
                logger.warning(f"无法设置认证文件权限: {e}")

        print("认证信息已安全保存")
        logger.info("认证配置已保存")

    except Exception as e:
        logger.error(f"保存认证配置失败: {e}")
        raise ValueError(f"保存认证配置失败: {e}")


def _save_auth_settings(config, auth_method, save_auth_info):
    """
    只保存认证设置，不保存认证信息。

    参数:
        config: 配置对象
        auth_method: 认证方式
        save_auth_info: 是否保存认证信息
    """
    try:
        config['SETTINGS'] = {
            'auth_method': auth_method,
            'save_auth_info': str(save_auth_info)
        }

        safe_write_config(config, AUTH_CONFIG_FILE)
        logger.info("认证设置已保存")

    except Exception as e:
        logger.error(f"保存认证设置失败: {e}")
        raise ValueError(f"保存认证设置失败: {e}")


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


def update_course_config(config, new_courses):
    """
    更新配置文件中的课程信息。

    参数:
        config (ConfigParser): 配置对象
        new_courses (dict): 新课程信息字典

    返回:
        bool: 是否有更新
    """
    config_updated = False
    existing_courses = {
        section: dict(config[section])
        for section in config.sections()
        if section != 'DEFAULT'
    }

    # 处理新发现的课程
    for course_id, course in new_courses.items():
        course_id_str = str(course_id)

        if course_id_str not in config.sections():
            # 添加新课程
            logger.info(f"添加新课程：{course_id_str} - {course['courseName']}")
            print(f"发现新课程：{course['courseName']}")
            config[course_id_str] = {
                'course_code': course['courseCode'],
                'course_name': remove_invalid_chars(course['courseName']),
                'live_id': str(course['id']),
                'download': 'yes'
            }
            config_updated = True
        else:
            # 检查现有课程是否需要更新
            existing_course = existing_courses[course_id_str]
            if (existing_course.get('course_code') != course['courseCode'] or
                existing_course.get('course_name') != remove_invalid_chars(course['courseName']) or
                    existing_course.get('live_id') != str(course['id'])):

                logger.info(f"更新课程信息：{course_id_str} - {course['courseName']}")
                print(f"更新课程：{course['courseName']}")
                config[course_id_str] = {
                    'course_code': course['courseCode'],
                    'course_name': remove_invalid_chars(course['courseName']),
                    'live_id': str(course['id']),
                    'download': existing_course.get('download', 'yes')
                }
                config_updated = True

    return config_updated


def validate_config_structure(config):
    """
    验证配置文件的基本结构。

    参数:
        config (ConfigParser): 配置对象

    异常:
        configparser.Error: 当配置结构无效时
    """
    if 'DEFAULT' not in config:
        raise configparser.Error("配置文件缺少 DEFAULT 段")

    required_keys = ['user_id', 'term_year', 'term_id']
    for key in required_keys:
        if key not in config['DEFAULT']:
            raise configparser.Error(f"配置文件缺少必要的配置项: {key}")


def create_initial_config(args, default_year, default_term, config_file):
    """
    创建初始配置文件。

    参数:
        args: 命令行参数
        default_year: 默认学年
        default_term: 默认学期
        config_file: 配置文件路径

    返回:
        bool: 是否成功创建
    """
    try:
        from api import scan_courses

        # 获取用户输入或使用命令行参数
        if args.uid:
            user_id = args.uid
        else:
            user_id = input("请输入用户ID：").strip()

        if not validate_user_id(user_id):
            print("用户ID格式无效")
            return False

        term_year = args.year if args.year else default_year
        term_id = args.term if args.term else default_term
        video_type = args.video_type if args.video_type else 'both'

        # 验证学期参数
        if not validate_term_params(term_year, term_id):
            print("学期参数无效")
            return False

        # 扫描课程
        print("正在扫描课程...", end='', flush=True)
        try:
            courses = scan_courses(user_id, term_year, term_id)
            if not courses:
                print("\r" + " " * 50 + "\r没有找到任何课程，请检查用户ID和学期参数")
                return False
        except Exception as e:
            print("\r" + " " * 50 + "\r")
            error_msg = handle_exception(e, "扫描课程失败")
            print(f"{error_msg}")
            return False
        finally:
            print("\r" + " " * 50 + "\r", end='')

        # 创建配置文件
        try:
            config = configparser.ConfigParser()
            config['DEFAULT'] = {
                'user_id': user_id,
                'term_year': str(term_year),
                'term_id': str(term_id),
                'video_type': video_type
            }

            # 添加课程配置
            for course_id, course in courses.items():
                course_id_str = str(course_id)
                config[course_id_str] = {
                    'course_code': course['courseCode'],
                    'course_name': remove_invalid_chars(course['courseName']),
                    'live_id': str(course['id']),
                    'download': 'yes'
                }

            safe_write_config(config, config_file)
            print(f"配置文件已生成，包含 {len(courses)} 门课程")
            print("请修改配置文件 automation_config.ini 后按回车继续...")
            input()
            return True

        except Exception as e:
            error_msg = handle_exception(e, "创建配置文件失败")
            print(f"{error_msg}")
            return False

    except Exception as e:
        error_msg = handle_exception(e, "初始化配置失败")
        print(f"{error_msg}")
        return False


def update_existing_config(args, default_year, default_term, config, config_file):
    """
    更新现有配置文件。

    参数:
        args: 命令行参数
        default_year: 默认学年
        default_term: 默认学期
        config: 配置对象
        config_file: 配置文件路径

    返回:
        bool: 是否成功更新
    """
    try:
        from api import scan_courses

        user_id = args.uid if args.uid else config['DEFAULT']['user_id']
        term_year = args.year if args.year else int(config['DEFAULT'].get('term_year', default_year))
        term_id = args.term if args.term else int(config['DEFAULT'].get('term_id', default_term))

        # 处理旧配置文件兼容性
        video_type = args.video_type if args.video_type else config['DEFAULT'].get('video_type', 'both')

        # 验证参数
        if not validate_user_id(user_id) or not validate_term_params(term_year, term_id):
            print("配置文件中的参数无效")
            return False

        print(f"使用用户ID：{user_id}")
        logger.info(f"使用配置文件中的用户ID：{user_id}")

        # 重新扫描课程
        print("正在扫描课程...", end='', flush=True)
        try:
            new_courses = scan_courses(user_id, term_year, term_id)
        except Exception as e:
            print("\r" + " " * 50 + "\r")
            error_msg = handle_exception(e, "扫描课程失败")
            print(f"{error_msg}")
            return False
        finally:
            print("\r" + " " * 50 + "\r", end='')

        # 更新配置
        config_updated = update_course_config(config, new_courses)

        # 更新默认配置
        config['DEFAULT']['video_type'] = video_type
        config['DEFAULT']['term_year'] = str(term_year)
        config['DEFAULT']['term_id'] = str(term_id)

        # 保存更新后的配置
        try:
            safe_write_config(config, config_file)
        except Exception as e:
            error_msg = handle_exception(e, "保存配置文件失败")
            print(f"{error_msg}")
            return False

        # 如果有新课程，提示用户检查配置
        if config_updated:
            print("配置文件已更新，请修改配置文件 automation_config.ini 后按回车继续...")
            input()

        return True

    except Exception as e:
        error_msg = handle_exception(e, "更新配置失败")
        print(f"{error_msg}")
        return False
