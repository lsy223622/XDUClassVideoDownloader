"""Compatibility launcher for the package automation CLI."""

from pathlib import Path

from xduclassvideodownloader.core.paths import set_runtime_dir


set_runtime_dir(Path(__file__).resolve().parent)

from xduclassvideodownloader.cli.automation import *  # noqa: E402,F401,F403


if __name__ == "__main__":
    run()
