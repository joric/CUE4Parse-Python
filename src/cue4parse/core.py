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

# enable logger

clr.AddReference("Serilog")
clr.AddReference("Serilog.Sinks.Console")

import System
from Serilog import Log, LoggerConfiguration
from Serilog.Configuration import LoggerSinkConfiguration
from Serilog.Events import LogEventLevel

def _console(self, *args, **kwargs):
    console_method = next(
        method
        for typ in System.Reflection.Assembly.Load("Serilog.Sinks.Console").GetTypes()
        if typ.IsSealed and typ.IsAbstract
        for method in typ.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)
        if method.Name == "Console"
        and method.GetParameters()
        and method.GetParameters()[0].ParameterType == clr.GetClrType(LoggerSinkConfiguration)
    )
    params = console_method.GetParameters()
    values = [System.Type.Missing] * len(params)
    values[0] = self
    for i, arg in enumerate(args, 1):
        values[i] = arg
    for i, p in enumerate(params):
        if p.Name == "standardErrorFromLevel":
            values[i] = LogEventLevel.Verbose
    for name, val in kwargs.items():
        for i, p in enumerate(params):
            if p.Name == name:
                values[i] = val
                break
    return console_method.Invoke(None, System.Array[System.Object](values))

setattr(LoggerSinkConfiguration, "Console", _console)

Log.Logger = LoggerConfiguration().MinimumLevel.Verbose().WriteTo.Console().CreateLogger()
