"""
视频合并模块
使用FFmpeg将PPT视频和教师视频合并为单个视频文件
"""
import os
import subprocess

# 默认视频编码器
coder = "libx264"

def has_nvidia_gpu():
    """
    检测系统是否安装了NVIDIA GPU及其驱动。
    
    返回:
        bool: 如果检测到NVIDIA GPU返回True，否则返回False
    """
    try:
        # 尝试运行nvidia-smi命令检测NVIDIA GPU
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        # 命令成功执行且输出包含NVIDIA字样时，说明存在NVIDIA GPU
        return result.returncode == 0 and "NVIDIA" in result.stdout
    except FileNotFoundError:
        # nvidia-smi命令不存在，说明没有安装NVIDIA驱动
        return False

# 根据GPU检测结果选择编码器
if has_nvidia_gpu():
    coder = "h264_nvenc"  # 使用NVIDIA硬件编码器
    print("检测到 NVIDIA GPU")
else:
    coder = "libx264"  # 使用软件编码器
    print("未检测到 NVIDIA GPU")
    

def find_matching_files(directory):
    """
    在目录中查找匹配的 pptVideo.ts 和 teacherTrack.ts 文件。
    
    参数:
        directory (str): 要搜索的目录路径
        
    返回:
        dict: 匹配的文件对字典，键为文件前缀，值为(ppt_file_path, teacher_file_path)元组
    """
    # 获取目录中的所有文件
    files = os.listdir(directory)
    # 筛选出PPT视频文件和教师视频文件
    ppt_files = [f for f in files if f.endswith("-pptVideo.ts")]
    teacher_files = [f for f in files if f.endswith("-teacherTrack.ts")]

    # 创建匹配文件对的字典
    matches = {}
    for ppt_file in ppt_files:
        # 提取文件名前缀（去掉 -pptVideo.ts 后缀）
        prefix = ppt_file.replace("-pptVideo.ts", "")
        # 查找对应的教师视频文件
        teacher_file = f"{prefix}-teacherTrack.ts"
        if teacher_file in teacher_files:
            # 构建完整路径并添加到匹配字典
            matches[prefix] = (os.path.join(directory, ppt_file), os.path.join(directory, teacher_file))
    return matches

def merge_videos(ppt_file, teacher_file, output_file):
    """
    使用 FFmpeg 将PPT视频和教师视频合并为单个视频文件。
    
    参数:
        ppt_file (str): PPT视频文件路径
        teacher_file (str): 教师视频文件路径
        output_file (str): 输出文件路径
        
    异常:
        subprocess.CalledProcessError: 当FFmpeg命令执行失败时抛出
    """
    print(f"正在合并: {ppt_file} 和 {teacher_file} -> {output_file}")
    
    # 构建FFmpeg命令参数
    command = [
        "ffmpeg",
        "-i", teacher_file,  # 输入1：教师视频
        "-i", ppt_file,      # 输入2：PPT视频
        "-c:v", coder,       # 视频编码器（CPU或GPU加速）
        "-preset", "slow",   # 编码预设：slow提供更好的压缩效果
        "-crf", "32",        # 视频质量：32提供适中的质量和文件大小
        "-b:v", "500k",      # 视频目标码率：500kbps
        "-maxrate", "600k",  # 最大码率：控制瞬时质量峰值
        "-bufsize", "2000k", # 缓冲区大小：适配码率变化
        "-r", "20",          # 帧率：20fps降低文件大小
        "-y",                # 自动覆盖输出文件
        "-v", "verbose",     # 详细输出模式
        "-stats",            # 显示编码统计信息
        # 复杂的视频滤镜：将PPT视频和教师视频并排显示
        "-filter_complex", "[1:v][0:v]scale2ref=main_w:ih[sec][pri];[sec]setsar=1,drawbox=c=black:t=fill[sec];[pri][sec]hstack[canvas];[canvas][1:v]overlay=main_w-overlay_w",
        output_file
    ]
    print("DEBUG: "+str(command))
    # 执行FFmpeg命令
    subprocess.run(command, check=True)

def process_directory(directory, output_dir):
    """
    处理目录中的所有文件，查找并合并匹配的视频文件。
    
    参数:
        directory (str): 输入目录路径，包含待合并的视频文件
        output_dir (str): 输出目录路径，存放合并后的视频文件
    """
    # 查找目录中匹配的PPT和教师视频文件对
    matches = find_matching_files(directory)
    if not matches:
        print("未找到匹配的文件对。")
        return

    # 创建输出目录（如果不存在）
    os.makedirs(output_dir, exist_ok=True)

    # 遍历所有匹配的文件对并逐个合并
    for prefix, (ppt_file, teacher_file) in matches.items():
        # 构建输出文件路径
        output_file = os.path.join(output_dir, f"{prefix}-merged.mkv")
        print(f"正在合并: {ppt_file} 和 {teacher_file} -> {output_file}")
        try:
            # 执行视频合并
            merge_videos(ppt_file, teacher_file, output_file)
            print(f"合并完成: {output_file}")
        except subprocess.CalledProcessError as e:
            # 合并失败时记录错误
            print(f"合并失败: {e}")


# 主程序入口
# 设置输入目录和输出目录
input_directory = os.getcwd()  # 当前工作目录作为输入目录
print("HELLO")
print(input_directory)
output_directory = os.path.join(input_directory, "out")  # 在当前目录下创建out文件夹作为输出目录

# 开始处理目录中的视频文件
process_directory(input_directory, output_directory)