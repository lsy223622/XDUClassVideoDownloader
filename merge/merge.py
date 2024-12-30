import os
import subprocess


coder = "libx264"

def has_nvidia_gpu():
    try:
        # 运行 nvidia-smi 命令
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        # 如果命令成功执行并返回输出，说明存在 NVIDIA GPU
        return result.returncode == 0 and "NVIDIA" in result.stdout
    except FileNotFoundError:
        # 如果 nvidia-smi 命令不存在，说明没有 NVIDIA GPU
        return False

# 检测是否有 NVIDIA GPU
if has_nvidia_gpu():
    coder = "h264_nvenc"
    print("检测到 NVIDIA GPU")
else:
    coder = "libx264"
    print("未检测到 NVIDIA GPU")
    

def find_matching_files(directory):
    """
    在目录中查找匹配的 pptVideo.ts 和 teacherTrack.ts 文件
    """
    files = os.listdir(directory)
    ppt_files = [f for f in files if f.endswith("-pptVideo.ts")]
    teacher_files = [f for f in files if f.endswith("-teacherTrack.ts")]

    # 创建一个字典，用于存储匹配的文件对
    matches = {}
    for ppt_file in ppt_files:
        # 提取文件名前缀（去掉 -pptVideo.ts）
        prefix = ppt_file.replace("-pptVideo.ts", "")
        # 查找对应的 teacherTrack.ts 文件
        teacher_file = f"{prefix}-teacherTrack.ts"
        if teacher_file in teacher_files:
            matches[prefix] = (os.path.join(directory, ppt_file), os.path.join(directory, teacher_file))
    return matches

def merge_videos(ppt_file, teacher_file, output_file):
    """
    使用 ffmpeg 合并两个视频
    """
    print(f"正在合并: {ppt_file} 和 {teacher_file} -> {output_file}")
    command = [
        "ffmpeg",
        "-i", teacher_file,
        "-i", ppt_file,
        "-c:v", coder,  # 使用 NVENC 编码压缩
        "-preset", "slow",  # 编码速度设置为 slow
        "-crf", "32",  # 视频质量设置为 32
        "-b:v", "500k",  # 视频目标码率设置为 1000kbps
        "-maxrate", "600k",  # 最大码率，控制瞬时质量
        "-bufsize", "2000k",  # 缓冲区大小，适配码率变化
        "-r", "20",  # 设置帧率为 20fps
        "-y",  # 覆盖输出文件
        "-v", "verbose",
        "-stats",
        "-filter_complex", "[1:v][0:v]scale2ref=main_w:ih[sec][pri];[sec]setsar=1,drawbox=c=black:t=fill[sec];[pri][sec]hstack[canvas];[canvas][1:v]overlay=main_w-overlay_w",
        output_file
    ]
    print("DEBUG: "+str(command))
    subprocess.run(command, check=True)

def process_directory(directory, output_dir):
    """
    处理目录中的所有文件，合并匹配的视频
    """
    # 查找匹配的文件对
    matches = find_matching_files(directory)
    if not matches:
        print("未找到匹配的文件对。")
        return

    # 创建输出目录（如果不存在）
    os.makedirs(output_dir, exist_ok=True)

    # 遍历匹配的文件对并合并
    for prefix, (ppt_file, teacher_file) in matches.items():
        output_file = os.path.join(output_dir, f"{prefix}-merged.mkv")
        print(f"正在合并: {ppt_file} 和 {teacher_file} -> {output_file}")
        try:
            merge_videos(ppt_file, teacher_file, output_file)
            print(f"合并完成: {output_file}")
        except subprocess.CalledProcessError as e:
            print(f"合并失败: {e}")


# 设置输入目录和输出目录
input_directory = os.getcwd()  # 当前目录
print("HELLO")
print(input_directory)
output_directory = os.path.join(input_directory, "out")  # 当前目录下的 out 文件夹

# 处理目录中的文件
process_directory(input_directory, output_directory)