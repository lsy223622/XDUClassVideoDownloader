@echo off
rem 禁用回显并启用延迟扩展
setlocal enabledelayedexpansion

for /R %%f in (*.ts) do (
    rem 获取不带扩展名的文件名
    set "output=%%~dpnf.mp4"

    rem 检查是否已经存在同名 mp4 文件
    if exist "%%~dpnf.mp4" (
        echo 文件 %%~dpnf.mp4 已经存在，跳过...
    ) else (
        echo 正在将 %%f 转换为 MP4 文件...
        ffmpeg -i "%%f" -c copy -movflags faststart "%%~dpnf.mp4" > NUL 2>&1

        rem 检查目标文件是否成功生成
        if exist "%%~dpnf.mp4" (
            rem 获取源文件和目标文件的大小
            for %%I in ("%%f") do set "sourceSize=%%~zI"
            for %%I in ("%%~dpnf.mp4") do set "targetSize=%%~zI"

            rem 比较文件大小，如果目标文件≥源文件的50%
            set /A threshold=!sourceSize! / 2
            if !targetSize! GEQ !threshold! (
                rem 删除源文件
                del "%%f"
                echo 成功转换 %%f，源文件已删除。
            ) else (
                echo 警告：转换结果可能不完整，目标文件小于源文件的50%。
            )
        ) else (
            echo 转换失败：目标文件 %%~dpnf.mp4 不存在。
        )
    )
)

echo 所有 TS 文件已处理完毕。
pause
