"""5.x compatibility launcher for the single-course CLI."""

from pathlib import Path

from xduclassvideodownloader.core.paths import set_runtime_dir

set_runtime_dir(Path(__file__).resolve().parent)

from xduclassvideodownloader.cli.single import *  # noqa: F401,F403,E402


if __name__ == "__main__":
    run()
