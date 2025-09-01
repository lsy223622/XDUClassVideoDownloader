# XDU Class Video Downloader

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

XDU Class Video Downloader is a Python application for downloading course videos from Xi'an University of Electronic Science and Technology's recording platform. It consists of two main Python scripts and supporting utilities.

## Working Effectively

- **Bootstrap and run the repository**:
  - `pip install requests tqdm psutil` -- installs required dependencies in under 10 seconds
  - `python3 XDUClassVideoDownloader.py --help` -- basic downloader, starts immediately (0.1s)
  - `python3 Automation.py --help` -- automated downloader, starts immediately (0.1s)

- **Key scripts and timing**:
  - `python3 XDUClassVideoDownloader.py` -- interactive mode for downloading specific courses by liveId
  - `python3 Automation.py` -- automated mode for downloading all semester courses by user UID
  - Both applications check for updates on startup (network request may fail in restricted environments - this is normal)

- **Binary dependencies**:
  - `chmod +x vsd-upx` -- make video downloader binary executable
  - `./vsd-upx --help` -- video stream downloader, works immediately
  - FFmpeg is optional (not available in this environment) - used only for TS to MP4 conversion

## Validation

- **ALWAYS test application startup after making changes**:
  - Run `python3 XDUClassVideoDownloader.py --help` and verify help output appears
  - Run `python3 Automation.py --help` and verify help output appears
  - Both should complete in under 1 second
- **Manual validation scenarios**:
  - **Basic functionality test**: Run `python3 -c "from api import get_initial_data; print('API import OK')"` -- should complete in 0.1s
  - **Module import test**: Run `python3 -c "import tqdm, psutil, requests; print('Dependencies OK')"` -- should complete instantly
  - **Binary test**: Run `./vsd-upx --help` -- should show video downloader help immediately
- **NEVER attempt actual video downloads in validation** - the applications require specific university credentials and course IDs that are not available in the development environment

## Common Tasks

The following are outputs from frequently run commands. Reference them instead of viewing, searching, or running bash commands to save time.

### Repository root structure
```
.
├── Automation.py                    # Main automated downloader script
├── XDUClassVideoDownloader.py      # Main basic downloader script  
├── api.py                          # API functions for course data
├── downloader.py                   # Download logic and utilities
├── utils.py                        # Utility functions
├── vsd-upx                         # Video stream downloader binary (Linux)
├── vsd-upx.exe                     # Video stream downloader binary (Windows)
├── merge/                          # Video merging utilities
│   ├── merge.py                    # Python script for merging videos
│   └── mergeUsage.md              # Usage instructions for merge utility
├── *.bat                          # Windows batch files for easy execution
├── README.md                       # Comprehensive usage documentation
└── config.ini                     # Generated configuration file (after first run)
```

### Dependencies from README.md
```python
# Required packages (install with pip)
pip install requests tqdm psutil

# requests - HTTP requests for API calls
# tqdm - Progress bars for downloads  
# psutil - System monitoring for optimal threading
```

### Application command-line interfaces
```bash
# XDUClassVideoDownloader.py usage
python XDUClassVideoDownloader.py [LIVEID] [-s] [-c COMMAND] [--no-merge] [--video-type {both,ppt,teacher}]

# Automation.py usage  
python Automation.py [-u UID] [-y YEAR] [-t {1,2}] [--video-type {both,ppt,teacher}]
```

## Key Projects in This Codebase

1. **XDUClassVideoDownloader.py** - Basic downloader for specific courses
   - Requires manual input of liveId (course identifier)
   - Interactive prompts for download options
   - Single course/video focused

2. **Automation.py** - Advanced automated downloader
   - Scans entire semester courses by user UID
   - Manages config.ini for course preferences
   - Incremental downloads (skips existing files)
   - Automatic course discovery

3. **Supporting modules**:
   - **api.py** - Handles API calls to university servers, includes version checking
   - **downloader.py** - Core download logic using vsd-upx binary
   - **utils.py** - Configuration management, file operations, threading optimization
   - **merge/** - Video merging utilities for combining course segments

## Important Locations

- **Main entry points**: `XDUClassVideoDownloader.py` and `Automation.py` in repository root
- **API integration**: `api.py` contains all external API calls and data parsing
- **Configuration**: `config.ini` is generated after first run of Automation.py
- **Binary dependencies**: `vsd-upx` (Linux) and `vsd-upx.exe` (Windows) for video downloading
- **Documentation**: `README.md` contains comprehensive Chinese documentation with examples

## Known Limitations and Workarounds

- **Network connectivity**: Update checking fails in restricted environments - this is expected and non-fatal
- **FFmpeg dependency**: Optional for TS to MP4 conversion - not available in sandboxed environments
- **University credentials**: Actual functionality requires valid university UID and course access
- **Chinese interface**: Applications use Chinese language prompts and error messages
- **No automated tests**: Repository has no test suite - validate changes through manual application startup

## Working with This Codebase

- **Always run dependency installation first**: `pip install requests tqdm psutil`
- **Test imports after changes**: Use quick import tests to validate module integrity
- **Focus on application startup**: The key validation is that both main scripts show help output correctly
- **Respect the binary**: The `vsd-upx` binary is compressed and should not be modified
- **Configuration is dynamic**: `config.ini` is generated at runtime based on user's course enrollment