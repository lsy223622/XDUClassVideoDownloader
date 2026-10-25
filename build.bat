@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "RESULT=1"
set "STAGING="
set "VERSION="
set "PROGRAMS=XDUClassVideoDownloader Automation WebUI"

if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv\Scripts\python.exe. Create the project virtual environment first.
    goto finish
)

for /f "tokens=3" %%V in ('findstr /b "__version__" "xduclassvideodownloader\_version.py"') do set "VERSION=%%~V"
if not defined VERSION (
    echo Cannot read the version from _version.py.
    goto finish
)

for %%P in (%PROGRAMS%) do (
    if exist "dist\%%P_v%VERSION%-beta.exe" (
        echo Output already exists: %%P_v%VERSION%-beta.exe. Update _version.py first.
        goto finish
    )
)

set "BUILD_DIST=build\release-%RANDOM%-%RANDOM%"
mkdir "%BUILD_DIST%" >nul 2>&1
if errorlevel 1 goto finish
set "STAGING=%BUILD_DIST%"

for %%P in (%PROGRAMS%) do (
    ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%STAGING%" "%%P.spec"
    if errorlevel 1 goto finish
)

for %%P in (%PROGRAMS%) do if not exist "%STAGING%\%%P.exe" goto finish
if not exist dist mkdir dist
if errorlevel 1 goto finish

for %%P in (%PROGRAMS%) do (
    echo N|move /-Y "%STAGING%\%%P.exe" "dist\%%P_v%VERSION%-beta.exe" >nul
    if errorlevel 1 goto finish
    if exist "%STAGING%\%%P.exe" goto finish
)
set "RESULT=0"
echo Build complete: dist\*_v%VERSION%-beta.exe

:finish
if defined STAGING (
    for %%P in (%PROGRAMS%) do if exist "%STAGING%\%%P.exe" del /q "%STAGING%\%%P.exe"
    rmdir "%STAGING%" 2>nul
)
if not "%RESULT%"=="0" echo Build stopped. Existing programs have been kept.
popd
pause
exit /b %RESULT%
