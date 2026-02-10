#!/usr/bin/env python3
"""
XDUClassVideoDownloader 的 GUI 启动器 (基于 Gooey)
"""
import sys
import logging
from gooey import Gooey, GooeyParser

# 导入原有核心逻辑
from XDUClassVideoDownloader import main as core_main
from config import get_auth_cookies, has_valid_auth_cookies, safe_write_config, AUTH_CONFIG_FILE
from api import login_to_chaoxing_via_ids, get_three_cookies_from_login, check_update
from utils import enable_debug_file_logging, setup_logging
import configparser

@Gooey(
    program_name="西电课件视频下载器",
    program_description="下载录直播平台的课程视频 (GUI版)",
    language='chinese',           # 设置中文界面
    default_size=(600, 850),      # 窗口大小 (加高以容纳认证选项)
    encoding="utf-8",             # 编码设置
    progress_regex=r"^进度: (?P<current>\d+)/(?P<total>\d+)$", # 匹配进度条
    richtext_controls=True,       # 启用富文本日志
    tabbed_groups=True,           # 使用分组标签页
    menu=[{
        'name': '帮助',
        'items': [{
            'type': 'Link',
            'menuTitle': '项目主页',
            'url': 'https://github.com/lsy223622/XDUClassVideoDownloader'
        }]
    }]
)
def main():
    # 调整日志级别，确保 GUI 能看到 INFO 信息
    root_logger = logging.getLogger("xdu")
    for handler in root_logger.handlers:
        if handler.name == "xdu_console":
            handler.setLevel(logging.INFO)

    parser = GooeyParser(description="西安电子科技大学录直播平台课程视频下载工具")

    # ================== 核心功能页 ==================
    main_group = parser.add_argument_group("下载设置", "核心下载参数")
    
    main_group.add_argument(
        "liveid", 
        metavar="课程 LiveID",
        help="请输入课程的 LiveID (纯数字)",
        widget="TextField"
    )

    main_group.add_argument(
        "--mode_selection",
        metavar="分节处理",
        choices=["自动合并 (默认)", "单节课模式 (不合并)", "半节课模式 (极细粒度)"],
        default="自动合并 (默认)",
        help="选择视频文件的保存方式"
    )

    main_group.add_argument(
        "--video_type",
        metavar="视频类型",
        choices=["both", "ppt", "teacher"],
        default="both",
        help="both=双流合成, ppt=仅演示文档, teacher=仅教师画面"
    )

    main_group.add_argument(
        "--skip_weeks",
        metavar="跳过周次",
        default="",
        help="格式示例: 5, 1-5. 留空则下载全部."
    )

    # ================== 认证设置页 ==================
    auth_group = parser.add_argument_group("认证设置 (首次运行必填)", "如果您尚未配置过auth.ini，请在此填写")
    
    auth_group.add_argument(
        "--auth_method",
        metavar="登录方式",
        choices=["无需更新 (已登录)", "统一身份认证 (IDS)", "超星账号密码"],
        default="无需更新 (已登录)",
        help="如果 auth.ini 已存在且有效，选择默认即可；否则请选择登录方式"
    )
    
    auth_group.add_argument(
        "--username",
        metavar="账号/学号",
        default="",
        help="输入您的学号或超星用户名"
    )
    
    auth_group.add_argument(
        "--password",
        metavar="密码",
        default="",
        widget="PasswordField",
        help="输入您的密码"
    )
    
    auth_group.add_argument(
        "--save_cred",
        metavar="保存密码到本地",
        action="store_true",
        default=False,
        help="勾选后将明文保存账号密码到配置文件 (方便下次免输入)"
    )

    # ================== 高级选项 ==================
    adv_group = parser.add_argument_group("高级选项")
    adv_group.add_argument(
        "--debug", 
        action="store_true", 
        default=False, 
        help="启用调试日志 (写入 logs/debug.log)"
    )

    args = parser.parse_args()

    # --- 0. 日志与更新检查 ---
    if args.debug:
        enable_debug_file_logging()
    
    try:
        check_update()
    except Exception:
        pass

    # --- 1. 处理认证逻辑 ---
    # 如果用户选择了登录方式，我们在 main 执行前先进行登录并写入配置
    if args.auth_method != "无需更新 (已登录)":
        if not args.username or not args.password:
            print("错误：选择登录方式时，必须填写账号和密码！")
            sys.exit(1)
            
        print(f"正在尝试使用 [{args.auth_method}] 进行登录...")
        try:
            cookies = {}
            auth_method_code = "" # ids, chaoxing, cookies
            
            if "统一身份认证" in args.auth_method:
                cookies = login_to_chaoxing_via_ids(args.username, args.password)
                auth_method_code = "ids"
            elif "超星" in args.auth_method:
                cookies = get_three_cookies_from_login(args.username, args.password)
                auth_method_code = "chaoxing"
            
            if not has_valid_auth_cookies(cookies):
                print("错误：登录似乎成功，但未获取到完整的 Cookie。")
                sys.exit(1)
            
            # 手动构建并写入配置文件 (模拟 config.py 的 _save_auth_config 逻辑)
            # 因为原有的 _save_auth_config 是私有函数且逻辑耦合了交互
            conf = configparser.ConfigParser()
            try:
                conf.read(AUTH_CONFIG_FILE, encoding='utf-8')
            except:
                pass
            
            # 写入基础设置
            conf["SETTINGS"] = {
                "auth_method": auth_method_code, 
                "save_auth_info": str(args.save_cred)  # 这里原逻辑是 save_auth_info 指"是否保存登录凭据以便自动刷新"
            }
            
            # 写入 Cookies (这是最重要的)
            conf["AUTH"] = {k: v for k, v in cookies.items() if k in ["_d", "UID", "vc3"]}
            
            # 如果用户选择保存密码
            if args.save_cred:
                if auth_method_code == "ids":
                    conf["IDS_CREDENTIALS"] = {"username": args.username, "password": args.password}
                elif auth_method_code == "chaoxing":
                    conf["CHAOXING_CREDENTIALS"] = {"username": args.username, "password": args.password}
            
            safe_write_config(conf, AUTH_CONFIG_FILE)
            print("登录成功！认证信息已保存到 auth.ini")
            
        except Exception as e:
            print(f"登录失败: {e}")
            sys.exit(1)

    # --- 2. 参数转换 ---

    # 将 GUI 的中文选项转换为核心逻辑需要的参数
    single_val = 0
    if "单节课" in args.mode_selection:
        single_val = 1
    elif "半节课" in args.mode_selection:
        single_val = 2
    
    # 转换 skip weeks
    skip_weeks_str = args.skip_weeks if args.skip_weeks else ""

    # 启用日志
    if args.debug:
        enable_debug_file_logging()

    # 检查更新
    try:
        check_update()
    except Exception:
        pass

    # 核心调用
    # 注意：Gooey 会捕获 stdout 实时显示
    print(f"正在启动下载任务... LiveID: {args.liveid}")
    
    success = core_main(
        liveid=args.liveid,
        single=single_val,
        merge=True,  # 默认开启合并功能 (除非用户添加专门的 no-merge 选项，这里为了界面简洁省略)
        video_type=args.video_type,
        skip_weeks=skip_weeks_str
    )

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
