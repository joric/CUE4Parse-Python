@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "LIBS_DIR=%LOCALAPPDATA%\cue4parse\libs"
set "TMP_DIR=%TEMP%\cue4parse-setup"

echo === cue4parse dependency setup (Windows) ===

if exist "%TMP_DIR%" rmdir /s /q "%TMP_DIR%"
mkdir "%TMP_DIR%"

rem add "goto git" here if you want to build dlls locally

echo Downloading fmodel
for /f "usebackq tokens=*" %%i in (`powershell -command "(Invoke-RestMethod -Uri 'https://api.fmodel.app/v1/infos/Qa').downloadUrl"`) do set DOWNLOAD_URL=%%i
if errorlevel 1 goto git

curl.exe -L -o "%TMP_DIR%\FModel.zip" "%DOWNLOAD_URL%" || goto git
powershell -command "Expand-Archive -Force '%TMP_DIR%\FModel.zip' '%TMP_DIR%'" || goto git

where dotnet >nul 2>&1 || (
    echo Installig dotnet
    winget install Microsoft.DotNet.SDK.10 --accept-package-agreements --accept-source-agreements || goto git
)

where sfextract >nul 2>&1 || (
    echo Installig sfextract
    dotnet tool install -g sfextract || goto git
)

echo Running sfextract
sfextract "%TMP_DIR%\FModel.exe" --output "%LIBS_DIR%" || goto git

goto success

:git

:: Check git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: git is required. Install from https://git-scm.com
    exit /b 1
)

:: Check/install dotnet
where dotnet >nul 2>&1
if %errorlevel% neq 0 (
    echo dotnet not found. Installing via winget...
    winget install Microsoft.DotNet.SDK.10 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dotnet. Install manually: https://dotnet.microsoft.com/download
        exit /b 1
    )
    :: Refresh PATH so dotnet is available in this session
    for /f "tokens=*" %%i in ('where dotnet 2^>nul') do set "DOTNET_PATH=%%i"
    if "!DOTNET_PATH!"=="" (
        set "PATH=%PATH%;%ProgramFiles%\dotnet"
    )
)


echo Cloning CUE4Parse...
git clone --depth=1 https://github.com/FabianFG/CUE4Parse.git "%TMP_DIR%\CUE4Parse"
if %errorlevel% neq 0 (echo ERROR: git clone failed. && exit /b 1)

:: Build
echo Building...

set "SLN=%TMP_DIR%\CUE4Parse\CUE4Parse.slnx"
if not exist "%SLN%" (
    echo ERROR: CUE4Parse.slnx not found.
    exit /b 1
)

echo Building solution...
dotnet publish "%SLN%" --configuration Release --output "%TMP_DIR%\build" --self-contained false  --runtime win-x64

if %errorlevel% neq 0 (echo ERROR: Build failed. && exit /b 1)

:: Copy DLLs
echo Copying libraries to %LIBS_DIR% ...
if not exist "%LIBS_DIR%" mkdir "%LIBS_DIR%"
set COUNT=0
for %%f in ("%TMP_DIR%\build\*.dll") do (
    copy /y "%%f" "%LIBS_DIR%\" >nul
    set /a COUNT+=1
    echo   copied: %%~nxf
)
echo Copied !COUNT! libraries to %LIBS_DIR%

:success

:: Cleanup
rmdir /s /q "%TMP_DIR%"

echo.
echo Done. Libraries installed to %LIBS_DIR%
