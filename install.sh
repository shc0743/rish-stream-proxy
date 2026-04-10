#!/bin/bash
set -e

echo "=== Rish Stdout/Stderr Fix Installer ==="
echo

# Check dependencies
if ! which rish >/dev/null 2>&1; then
    echo "Error: rish not found. Install Shizuku and put rish to PATH first."
    exit 1
fi

if ! which python3 >/dev/null 2>&1; then
    echo "Error: python3 not found. Install python3."
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "1. Compiling rish_stream_proxy (if needed)..."
if [ ! -x "./rish_stream_proxy" ] || [ "./rish_stream_proxy.cpp" -nt "./rish_stream_proxy" ]; then
    if which clang++ >/dev/null 2>&1; then
        clang++ -std=c++17 -o rish_stream_proxy rish_stream_proxy.cpp
        echo "   Compiled successfully."
    else
        echo "   Warning: clang++ not found, using precompiled binary."
    fi
else
    echo "   Binary already up-to-date."
fi

echo "2. Making scripts executable..."
chmod +x rish.py 2>/dev/null || true
chmod +x rish_stream_proxy 2>/dev/null || true

echo "3. Copying proxy to remote shell..."
if ./rish.py --copy ./rish_stream_proxy; then
    echo "   Proxy copied successfully."
else
    echo "   Error: Failed to copy proxy to remote."
    echo "   You may need to copy it manually or check Shizuku status."
    exit 1
fi

echo
echo "=== Installation Complete ==="
echo
echo "Usage:"
echo "  rish.py -c 'command'  # Direct usage"
echo
echo "Files installed:"
echo "  - /data/user_de/0/com.android.shell/files/rish_stream_proxy - Remote proxy"
