import sys
import os
import subprocess
from pathlib import Path

from cue4parse import _DLL_DIR

PLATFORM = sys.platform

def natives_present() -> bool:
    glob = "*.dll" if PLATFORM == "win32" else "*.so"
    return _DLL_DIR.exists() and any(_DLL_DIR.glob(glob))

def _run_script(script: Path, *extra_args: str) -> int:
    """Run a script and return the returncode (0 for success, non-zero for failure)"""
    if not script.exists():
        raise RuntimeError(f"Setup script not found: {script}")
    args = [*extra_args, "--force"] if "--force" in sys.argv else list(extra_args)
    if PLATFORM == "win32":
        result = subprocess.run([str(script), *args], shell=True)
        return result.returncode
    else:
        result = subprocess.run(["bash", str(script), *args])
        return result.returncode

def main() -> None:
    if PLATFORM not in ("win32", "linux"):
        print(f"Unsupported platform: {PLATFORM}. Only Windows and Linux are supported.")
        sys.exit(1)

    if natives_present() and "--force" not in sys.argv:
        print(f"Already set up. Use --force to reinstall.")
        return

    scripts = Path(__file__).parent
    if PLATFORM == "win32":
        _run_script(scripts / "setup.bat")
    else:
        _run_script(scripts / "setup.sh")

if __name__ == "__main__":
    main()
