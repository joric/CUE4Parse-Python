#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBS_DIR="$HOME/.local/share/cue4parse/libs"

echo "=== cue4parse Linux dependency setup ==="

# Install dotnet if missing
if ! command -v dotnet &>/dev/null; then
    echo "dotnet not found, installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y dotnet-sdk-10.0
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y dotnet-sdk-10.0
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm dotnet-sdk
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y dotnet-sdk-10.0
    else
        echo "No supported package manager found. Installing via Microsoft script..."
        curl -fsSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0
        export DOTNET_ROOT="$HOME/.dotnet"
        export PATH="$DOTNET_ROOT:$DOTNET_ROOT/tools:$PATH"
    fi
fi

export PATH="$HOME/.dotnet/tools:$PATH"

# Clone and build CUE4Parse
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

for cmd in git make gcc; do
    command -v "$cmd" &>/dev/null || { echo "ERROR: $cmd is required. Install it with your package manager."; exit 1; }
done

echo "Cloning CUE4Parse..."
git clone --depth=1 https://github.com/FabianFG/CUE4Parse.git "$TMP/CUE4Parse"

echo "Building..."

SLN="$TMP/CUE4Parse/CUE4Parse.slnx"
if [ ! -f "$SLN" ]; then
    echo "ERROR: CUE4Parse.slnx not found."
    exit 1
fi

echo "Building solution..."
dotnet publish "$SLN" --configuration Release --output "$TMP/build" --self-contained false --runtime linux-x64

# Build Detex from source
echo "Building Detex..."
git clone --depth=1 https://github.com/hglm/detex "$TMP/detex"

# Set SHARED library configuration
sed -i 's/^LIBRARY_CONFIGURATION.*/LIBRARY_CONFIGURATION = SHARED/' "$TMP/detex/Makefile.conf"

# Patch detexDecompressTextureLinear to use DETEX_HELPER_SHARED_EXPORT
sed -i 's/DETEX_API bool detexDecompressTextureLinear/DETEX_HELPER_SHARED_EXPORT bool detexDecompressTextureLinear/' "$TMP/detex/detex.h"

make -C "$TMP/detex"
ls "$TMP/detex/"
cp $TMP/detex/libdetex.so* "$LIBS_DIR/Detex.so"
echo "  copied: Detex.so"

echo "Copying libraries to $LIBS_DIR..."
mkdir -p "$LIBS_DIR"
find "$TMP/build" \( -name "*.so" -o -name "*.so.*" -o -name "*.dll"  -o -name "*.runtimeconfig.json" \) -exec cp {} "$LIBS_DIR/" \;

echo "Done. Libraries installed to $LIBS_DIR"
