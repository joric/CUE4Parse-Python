from __future__ import annotations

import fnmatch
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import Flag, auto
from pathlib import Path
from typing import Any, Iterable

from cue4parse import _DLL_DIR

def _find_dotnet_root() -> Path | None:
    candidates = [
        Path.home() / ".dotnet",
        Path("/usr/share/dotnet"),
        Path("/usr/lib/dotnet"),
    ]
    for candidate in candidates:
        if (candidate / "host" / "fxr").exists():
            return candidate
    return None

def _find_runtime_config() -> str | None:
    libs_dir = Path(__file__).parent / "libs"
    configs = list(libs_dir.glob("*.runtimeconfig.json"))
    return str(configs[0]) if configs else None

dotnet_root = _find_dotnet_root()
if dotnet_root:
    os.environ["DOTNET_ROOT"] = str(dotnet_root)

import pythonnet

runtime_config = _find_runtime_config()
if runtime_config:
    pythonnet.load("coreclr", runtime_config=runtime_config)
else:
    pythonnet.load("coreclr")

import clr

libs_dir = _DLL_DIR
cue4parse_dll_dir = str(libs_dir)
sys.path.append(cue4parse_dll_dir)

clr.AddReference("CUE4Parse")
clr.AddReference("CUE4Parse-Conversion")

clr.AddReference("System")
clr.AddReference("System.Core")
clr.AddReference("Newtonsoft.Json")

clr.AddReference("Serilog")
clr.AddReference("Serilog.Sinks.Console")

import System
from Serilog import Log, LoggerConfiguration
from Serilog.Events import LogEventLevel
from Serilog.Configuration import LoggerSinkConfiguration

def with_console(cfg: LoggerConfiguration) -> LoggerConfiguration:
    asm = System.Reflection.Assembly.Load("Serilog.Sinks.Console")
    bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static
    lsc_t = clr.GetClrType(LoggerSinkConfiguration)
    for t in asm.GetTypes():
        if not (t.IsSealed and t.IsAbstract):
            continue
        for m in t.GetMethods(bf):
            if m.Name != "Console":
                continue
            ps = m.GetParameters()
            if len(ps) >= 1 and ps[0].ParameterType == lsc_t:
                args = [System.Type.Missing] * len(ps)
                args[0] = cfg.WriteTo
                # Find and set the standardErrorFromLevel parameter so it's stderr, not stdout
                for i, p in enumerate(ps):
                    if p.Name == "standardErrorFromLevel":
                        lel_t = System.Type.GetType("Serilog.Events.LogEventLevel, Serilog")
                        args[i] = System.Enum.Parse(lel_t, "Verbose")
                        break
                m.Invoke(None, System.Array[System.Object](args))
                return cfg
    raise RuntimeError("Serilog console sink extension method not found")

# you can re-define it in user code later with Verbose() or any other level
Log.Logger = with_console(LoggerConfiguration().MinimumLevel.Fatal()).CreateLogger()
