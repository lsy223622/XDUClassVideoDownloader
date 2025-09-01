# XDUClassVideoDownloader

XDUClassVideoDownloader is a Python-based tool for downloading class videos from Xi'an University of Electronic Science and Technology's live streaming platform. It supports both individual course downloads and automated semester-wide downloads.

**ALWAYS reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Environment Setup and Dependencies
- Install Python 3.8+ (tested with Python 3.12): `python3 --version`
- Install required Python dependencies: `python3 -m pip install requests tqdm psutil` (takes ~30 seconds)
- The project includes a pre-built `vsd-upx` binary for video downloading - ensure it's executable: `chmod +x vsd-upx`
- Optional: Install FFmpeg for TS-to-MP4 conversion: `apt-get install ffmpeg` (not required for basic functionality)

### Core Applications
- **XDUClassVideoDownloader.py**: Download specific courses by liveId
- **Automation.py**: Automated semester-wide course discovery and downloading
- Both applications check for updates on startup (may fail due to network restrictions - this is normal)

### Running the Applications

#### Basic Command Testing
- Check help: `python3 XDUClassVideoDownloader.py --help` (takes ~5 seconds due to update check)
- Check help: `python3 Automation.py --help` (takes ~5 seconds due to update check)
- All help commands complete within 10 seconds

#### XDUClassVideoDownloader.py Usage
- Interactive mode: `python3 XDUClassVideoDownloader.py`
- Command-line mode: `python3 XDUClassVideoDownloader.py [LIVEID] [-s] [--video-type {both,ppt,teacher}] [--no-merge]`
- Example: `python3 XDUClassVideoDownloader.py 1234567890 -s --video-type ppt`
- **CRITICAL**: Requires valid university liveId and network access to `newesxidian.chaoxing.com`

#### Automation.py Usage  
- Interactive mode: `python3 Automation.py`
- Command-line mode: `python3 Automation.py [-u UID] [-y YEAR] [-t {1,2}] [--video-type {both,ppt,teacher}]`
- Example: `python3 Automation.py -u 123456789 -y 2024 -t 1 --video-type both`
- **CRITICAL**: Requires valid university UID and network access to `newesxidian.chaoxing.com`

#### Configuration Management
- Automation.py creates `config.ini` on first run with discovered courses
- Configuration format:
  ```ini
  [DEFAULT]
  user_id = 123456789
  term_year = 2024
  term_id = 1  
  video_type = both

  [course_id]
  course_code = CS101
  course_name = CourseNameHere
  live_id = 1234567890
  download = yes
  ```
- **ALWAYS** verify `config.ini` is created when testing Automation.py
- To reset: delete `config.ini` and re-run Automation.py

### Video Processing
- Downloads create `.ts` video files in course-specific directories
- Supports automatic merging of video segments using `vsd-upx` binary
- Alternative merging with FFmpeg via `merge/merge.py` (requires FFmpeg installation)
- Video types: `both` (default), `ppt` (presentation video), `teacher` (instructor video)

## Validation

### Manual Testing Scenarios
- **ALWAYS** run applications with `--help` to verify basic functionality
- Test with dummy parameters to verify error handling: `python3 XDUClassVideoDownloader.py 1234567890`
- Expect network errors when not connected to university network - this is normal behavior
- **NEVER** run applications without parameters in testing environments (requires user input)

### Expected Behavior
- Applications fail gracefully with network errors when university servers are unreachable
- Update checks may fail - this is expected and does not affect core functionality  
- Both apps complete help commands within 10 seconds
- Dependency installation completes within 60 seconds
- Interactive mode requires university credentials and network access to function

### File System Validation
- Verify `vsd-upx` binary is executable: `ls -la vsd-upx` should show execute permissions
- Check for `config.ini` creation after running Automation.py
- Downloaded videos are saved in directories named like: `{YEAR}年{COURSE_CODE}{COURSE_NAME}`
- CSV files with M3U8 links are created alongside video directories

## Common Tasks and Key Information

### Network Dependencies
- **CRITICAL**: Both applications require network access to:
  - `api.lsy223622.com` (for version checking - may fail)
  - `newesxidian.chaoxing.com` (for course data and video downloads - required)
- Network failures are normal in non-university environments

### Timing Expectations
- Help commands: 5-10 seconds (due to update check)
- Dependency installation: 30-60 seconds 
- Course scanning: Variable depending on network (may fail outside university network)
- Video downloads: Variable depending on video size and network speed
- **NEVER CANCEL**: Applications may take several minutes to complete when downloading videos

### Binary Dependencies
- `vsd-upx`: Pre-built binary from [clitic/vsd](https://github.com/clitic/vsd) for video operations
- `vsd-upx.exe`: Windows version of the binary
- **DO NOT** try to build these binaries - they are provided pre-built
- Verify binary functionality: `./vsd-upx --help`

### Batch File Helpers (Windows)
- `windows_run.bat`: Wrapper for XDUClassVideoDownloader.py
- `automation.bat`: Wrapper for Automation.py  
- `ConvertTStoMP4(NeedFFmpeg).bat`: Convert downloaded TS files to MP4 format

### Alternative Video Merging
- `merge/merge.py`: FFmpeg-based video merging script
- Requires FFmpeg installation: `apt-get install ffmpeg`
- Usage: Place script in video directory and run `python3 merge.py`
- Creates merged videos with picture-in-picture layout

## Limitations and Known Issues
- Applications require valid university credentials (UID/liveId) to function fully
- Network connectivity to university servers is required for course discovery and downloads
- Update check may fail due to DNS restrictions - this does not affect core functionality
- No unit tests or automated testing infrastructure exists
- Interactive mode requires manual input - avoid in automated environments

## Repository Structure
```
.
├── XDUClassVideoDownloader.py    # Main course downloader
├── Automation.py                 # Automated semester downloader  
├── api.py                        # University API interactions
├── downloader.py                 # Video download and merge logic
├── utils.py                      # Utility functions
├── vsd-upx                       # Video processing binary (Linux)
├── vsd-upx.exe                   # Video processing binary (Windows)
├── merge/
│   ├── merge.py                  # Alternative FFmpeg-based merging
│   └── mergeUsage.md             # Merge script documentation
├── *.bat                         # Windows batch file helpers
└── config.ini                    # Generated configuration (after first run)
```