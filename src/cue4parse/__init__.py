import sys
import os
from pathlib import Path

_DLL_DIR = Path(os.environ.get('LOCALAPPDATA', os.path.expanduser('~/.local/share'))) / "cue4parse" / "libs"

if not _DLL_DIR.exists():
    print("DLLs not found. Downloading native libraries.")
    from cue4parse import setup_deps
    setup_deps.main()

from cue4parse.core import *
from cue4parse.includes import *
